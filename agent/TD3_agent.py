import numpy as np
import os
import logging
import random
import torch
import torch.optim as optim
import torch.nn.functional as F
import itertools
import copy
import warnings
warnings.filterwarnings("ignore", category=UserWarning)

from utils.replay_buffer import ReplayBuffer
from utils.decay import  LinearAnneal
from agent.base_agent import BaseAgent
from networks.model import TD3_Actor, TD3_Critic
from environment.env import TradingEnv


class TD3(BaseAgent):
    def __init__(self, env:TradingEnv, gamma:float, actor_lr, critic_lr, actor_tau, critic_tau,
                 policy_noise, noise_clip, exploration_noise, exploration_noise_end, policy_delay,
                 batch_size:int, memory_size:int, episodes:int, device:str, print_info:bool):
        super(BaseAgent).__init__(env, gamma, actor_lr, critic_lr, batch_size, memory_size, episodes, device)
        
        self.actor_tau = actor_tau
        self.critic_tau = critic_tau
        self.policy_noise = policy_noise
        self.noise_clip = noise_clip
        self.policy_delay = policy_delay
        self.print_info = print_info
        
        self.exploration_noise = LinearAnneal(exploration_noise, exploration_noise_end, self.episodes*150)
        
        self.s_dim = self.env.observation_space['observation'].shape
        self.a_dim = self.env.action_space.shape
        self.max_action = self.env.action_space.high.shape[0]
        self.csv = 'output/portfolio-management.csv'
        
        # initialize network
        self.actor = TD3_Actor(device=self.device).to(self.device)
        self.actor_target = copy.deepcopy(self.actor)
        self.actor_optimizer = optim.Adam(self.actor.parameters(), lr=self.actor_lr)
        
        self.critic = TD3_Critic(device=self.device).to(self.device)
        self.critic_target = copy.deepcopy(self.critic)
        self.critic_optimizer = optim.Adam(self.critic.parameters(), lr=self.critic_lr)
        
        self._log_init()
        self.replay_memory = ReplayBuffer(maxlen=self.memory_size, obs_dim=self.s_dim, action_dim=self.a_dim)
        self.itr = 0
    
    def _log_init(self):
        formatter = logging.Formatter(r'"%(asctime)s",%(message)s')
        self.logger = logging.getLogger("portfolio-optimizer")
        self.logger.setLevel(logging.INFO)
        fh = logging.FileHandler(f"output/Records.txt")
        fh.setFormatter(formatter)
        self.logger.addHandler(fh)
    
    def _soft_update(self, net_target:TD3_Actor, net:TD3_Critic, tau):
        for target_param, param in zip(net_target.parameters(), net.parameters()):
            target_param.data.copy_(target_param.data*(1.0-tau)+param.data*tau)
    
    def _choose_action(self, s0):
        with torch.no_grad():
            a0 =  self.actor(s0).squeeze(0).cpu().detach().numpy()
        return a0
    
    def _update_Q(self, s0, a0, r1, s1, mask):
        with torch.no_grad():
            # noise = torch.ones_like(a0).data.normal_(0, self.POLICY_NOISE).to(self.device)
            noise = self.policy_noise * torch.rand_like(a0).to(self.device)
            noise = noise.clip(-self.noise_clip, self.noise_clip)
            a1 = self.actor_target(s1) + noise
            a1 = a1.clip(0, 1)
            
            target_Q1, target_Q2 = self.critic_target(s1, a1)
            target_Q = torch.min(target_Q1, target_Q2)
            target_Q = r1 + mask * target_Q.detach()
        
        # Optimize Critic
        current_Q1, current_Q2 = self.critic(s0, a0) # both shape(batch_size)
        Q_loss = F.smooth_l1_loss(current_Q1, target_Q) + F.smooth_l1_loss(current_Q2, target_Q)
        self.critic_optimizer.zero_grad()
        Q_loss.backward()
        self.critic_optimizer.step()
        
    def _update_policy(self, s0):
        actor_loss = -torch.mean(self.critic(s0, self.actor(s0))[0])
        self.actor_optimizer.zero_grad()
        actor_loss.backward()
        self.actor_optimizer.step()
        
    def optimize(self):
        self.itr += 1
        if len(self.replay_memory) < self.batch_size:
            return
        
        # Increase batch size by the number of data in the replay memory
        k = 1 + len(self.replay_memory) / self.memory_size
        batch_size = int(k * self.batch_size)
        
        s0, a0, r1, s1, done = self.replay_memory.sample(batch_size)
        a0 = torch.tensor(a0, dtype=torch.float32, device=self.device)
        r1 = torch.tensor(r1, dtype=torch.float32, device=self.device).view(batch_size)
        done = torch.tensor(done, dtype=torch.float32, device=self.device)
        self._update_Q(s0, a0, r1, s1, done)
        
        if self.itr % self.policy_delay == 0:
            self._update_policy(s0)
            self._soft_update(self.actor_target, self.actor, self.actor_tau)
            self._soft_update(self.critic_target, self.critic, self.critic_tau)
            self.itr = 0
    
    def save_model(self, model_path='networks/saved_models/'):
        self.logger.info('Saving model...')
        torch.save(self.actor.state_dict(), os.path.join(model_path, 'actor.ckpt'))
        torch.save(self.actor_target.state_dict(), os.path.join(model_path, 'actor_target.ckpt'))
        torch.save(self.critic.state_dict(), os.path.join(model_path, 'critic.ckpt'))
        torch.save(self.critic_target.state_dict(), os.path.join(model_path, 'critic_target.ckpt'))
    
    def load_model(self, model_path='networks/saved_models/'):
        self.logger.info('Load model...')
        self.actor.load_state_dict(torch.load(os.path.join(model_path, 'actor.ckpt')))
        self.actor_target.load_state_dict(torch.load(os.path.join(model_path, 'actor_target.ckpt')))
        self.critic.load_state_dict(torch.load(os.path.join(model_path,'critic.ckpt')))
        self.critic_target.load_state_dict(torch.load(os.path.join(model_path,'critic_target.ckpt')))
    
    def train(self):
        self.logger.info('Start training...')
        episode_reward_list = []
        for episode in range(self.episodes):
            s0 = self.env.reset()
            episode_reward = 0
            done = False
            for step in itertools.count():
                a0 = self._choose_action(s0)
                
                # add noise to action
                a0 += np.random.normal(0, self.exploration_noise.anneal(), size=self.env.action_space.shape[0])
                s1, r1, done, info = self.env.step(a0)
                self.replay_memory.update(s0['observation'], a0, r1, done)
                if self.print_info:
                    print(info)
                episode_reward += r1
                s0 = s1
                self.optimize()
                
                if done:
                    break
                
            self.logger.info(f"Episode: {episode+1} | Total Reward: {episode_reward} | Portfolio Value: {info['portfolio_value']} | Market Value: {info['market_value']}")
            episode_reward_list.append(episode_reward)

            if episode_reward >= max(episode_reward_list):
                self.save_model('networks/saved_models/third_stage')
    
    def pretrain(self, pretrain_step):
        self.logger.info('Filling replay buffer...')
        finish = False
        n_steps = 0
        with torch.no_grad():
            while not finish:
                state = self.env.reset()
                for _ in range(pretrain_step):
                    action = np.random.random(8)
                    next_state, reward, done, _ = self.env.step(action)
                    self.update_memory(state, action, reward, next_state, done)
                    state = next_state
                    n_steps += 1
                    
                    if done:
                        break
                
                if n_steps >= pretrain_step:
                    self.logger.info('Filled replay buffer...')
                    finish = True
                    
    
    def test(self, model_path):
        self.logger.info('Start testing...')
        self.load_model(model_path)
        state = self.env.reset()
        while True:
            with torch.no_grad():
                action = self._choose_action(state)
            next_state, _, done, info = self.env.step(action)
            self.logger.info(f"Date: {info['date']} | Asset Weight: {info['weights']} | Cost: {info['cost']} | Portfolio Value: {info['portfolio_value']}")
            
            if done:
                break
            state = next_state