from environment.env import TradingEnv
from agent.TD3_agent import TD3

import torch

env = TradingEnv('data', observation_features='Close', commission=0.01, steps=750, start_date_index=0)


params = {
    'env': env,
    'device': torch.device('cuda'),
    'GAMMA':0.96,
    'CRITIC_LR':0.001,
    'ACTOR_LR':0.0001,
    'TAU_ACTOR': 0.05, # 0.05
    'TAU_CRITIC': 0.05,
    'BATCH_SIZE':64,
    'MEMORY_SIZE': 100000,
    'EPISODES': 100,
    'POLICY_NOISE': 0.0025,
    'NOISE_CLIP': 0.005,
    'POLICY_DELAY': 3,
    'EXPLORATION_NOISE':0.005,
    'EXPLORATION_NOISE_END':0.0005,
    'print_info': False
}


########### training stage 1 ###########
# 
# 
agent = TD3(**params)
# agent.pretrain(pretrain_step=50000)
agent.train(noise='Gaussian')