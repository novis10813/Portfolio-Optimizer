import numpy as np
import pandas as pd
import os
import logging
import random
import torch
import torch.nn as nn
import torch.optim as optim
import torch.nn.functional as F
import itertools
import copy

from collections import deque
from agent.model import TD3_Actor, TD3_Critic
from utils import  OUNoise, LinearAnneal


class TD3:
    def __init__(self, **kwargs):
        
        for key, value in kwargs.items():
            setattr(self, key, value)
        
        self.exploration_noise = LinearAnneal(self.EXPLORATION_NOISE, self.EXPLORATION_NOISE_END, self.EPISODES*150)
        
        # self.s_dim = self.env.observation_space.shape[0]
        # self.a_dim = self.env.action_space.shape[0]
        self.max_action = self.env.action_space.high.shape[0]
        self.csv = 'output/portfolio-management.csv'
        
        # initialize network
        self.actor = TD3_Actor(device=self.device).to(self.device)
        self.actor_target = copy.deepcopy(self.actor)
        self.actor_optimizer = optim.Adam(self.actor.parameters(), lr=self.ACTOR_LR)
        
        self.critic = TD3_Critic(device=self.device).to(self.device)
        self.critic_target = copy.deepcopy(self.critic)
        self.critic_optimizer = optim.Adam(self.critic.parameters(), lr=self.CRITIC_LR)
        
        self._log_init()
        self.replay_memory = deque(maxlen=self.MEMORY_SIZE)
        self.itr = 0
    
    def _log_init(self):
        formatter = logging.Formatter(r'"%(asctime)s",%(message)s')
        self.logger = logging.getLogger("portfolio-optimizer")
        self.logger.setLevel(logging.INFO)
        fh = logging.FileHandler(f"output/Records.csv")
        fh.setFormatter(formatter)
        self.logger.addHandler(fh)
    
    def _soft_update(self, net_target, net, tau):
        for target_param, param in zip(net_target.parameters(), net.parameters()):
            target_param.data.copy_(target_param.data*(1.0-tau)+param.data*tau)
    
    def _choose_action(self, s0):
        a0 =  self.actor(s0).squeeze(0).cpu().detach().numpy()
        return a0
    
    def _update_memory(self, *transitions):
        self.replay_memory.append(transitions)
    
    def _update_Q(self, s0, a0, r1, s1, done):
        with torch.no_grad():
            # noise = torch.ones_like(a0).data.normal_(0, self.POLICY_NOISE).to(self.device)
            noise = self.POLICY_NOISE * torch.rand_like(a0).to(self.device)
            noise = noise.clamp(-self.NOISE_CLIP, self.NOISE_CLIP)
            a1 = self.actor_target(s1) + noise
            a1 = a1.clamp(-self.max_action, self.max_action)
            
            target_Q1, target_Q2 = self.critic_target(s1, a1)
            target_Q = torch.min(target_Q1, target_Q2)
            target_Q = r1 + (1 - done) * self.GAMMA * target_Q.detach()
            # target_Q = r1 + self.GAMMA * target_Q.detach()
        
        # Optimize Critic
        current_Q1, current_Q2 = self.critic(s0, a0)
        Q_loss = F.smooth_l1_loss(current_Q1, target_Q) + F.smooth_l1_loss(current_Q2, target_Q)
        self.critic_optimizer.zero_grad()
        Q_loss.backward()
        self.critic_optimizer.step()
        
    def _update_policy(self, s0):
        actor_loss = -torch.mean(self.critic(s0, self.actor(s0))[0])
        self.actor_optimizer.zero_grad()
        actor_loss.backward()
        self.actor_optimizer.step()
        
    def _optimize(self):
        self.itr += 1
        if len(self.replay_memory) < self.BATCH_SIZE:
            return
        
        rand_num = random.randint(0, len(self.replay_memory)-self.BATCH_SIZE)
        batch = list(itertools.islice(self.replay_memory, rand_num, rand_num+self.BATCH_SIZE))
        
        s0, a0, r1, s1, done = zip(*batch)
        a0 = torch.tensor(a0, dtype=torch.float32, device=self.device)
        r1 = torch.tensor(r1, dtype=torch.float32, device=self.device).view(self.BATCH_SIZE,-1)
        done = torch.tensor(done, dtype=torch.float32, device=self.device)
        self._update_Q(s0, a0, r1, s1, done)
        
        if self.itr % self.POLICY_DELAY == 0:
            self._update_policy(s0)
            self._soft_update(self.actor_target, self.actor, self.TAU_ACTOR)
            self._soft_update(self.critic_target, self.critic, self.TAU_CRITIC)
            self.itr = 0
    
    def save_model(self, model_path='agent/saved_model/'):
        torch.save(self.actor.state_dict(), os.path.join(model_path, 'actor.ckpt'))
        torch.save(self.actor_target.state_dict(), os.path.join(model_path, 'actor_target.ckpt'))
        torch.save(self.critic.state_dict(), os.path.join(model_path, 'critic.ckpt'))
        torch.save(self.critic_target.state_dict(), os.path.join(model_path, 'critic_target.ckpt'))
    
    def load_model(self, model_path='agent/saved_model/'):
        self.actor.load_state_dict(torch.load(os.path.join(model_path, 'actor.ckpt')))
        self.actor_target.load_state_dict(torch.load(os.path.join(model_path, 'actor_target.ckpt')))
        self.critic.load_state_dict(torch.load(os.path.join(model_path,'critic.ckpt')))
        self.critic_target.load_state_dict(torch.load(os.path.join(model_path,'critic_target.ckpt')))
    
    def set_eval(self):
        self.actor.eval()
        self.actor_target.eval()
        self.critic.eval()
        self.critic_target.eval()
    
    def train(self, noise='Gaussian'):
        ou_noise = OUNoise(self.env.action_space)
        for episode in range(self.EPISODES):
            s0 = self.env.reset()
            episode_reward = 0
            done = False
            for step in itertools.count():
                # self.env.render()
                a0 = self._choose_action(s0)
                
                if noise == 'Gaussian':
                    a0 += np.random.normal(0, self.exploration_noise.anneal(), size=self.env.action_space.shape[0])
                    a0 = a0.clip(self.env.action_space.low, self.env.action_space.high)
                elif noise == 'OUNoise':
                    a0 = ou_noise.get_action(a0, step)
                    
                s1, r1, done, _ = self.env.step(a0)
                self._update_memory(s0, a0, r1, s1, done)
                
                episode_reward += r1
                s0 = s1
                self._optimize()   
                
                if done:
                    break
            
            self.logger.info(f"{episode},{step},{episode_reward:.1f}")
                
        print(f'Training Done! save model')
        self.save_model()
    
    def test(self, env, model_path='agent/saved_model/'):
        self.load_model(model_path)
        self.set_eval()
        state = env.reset()
        while True:
            with torch.no_grad():
                action = self._choose_action(state)
            next_state, _, done, info = env.step(action)
            
            if done:
                break
            state = next_state