# Portfolio Optimizer

Reinforcement learning portfolio optimizer with custom TD3 and DDPG agents, an EIIE-style model reference, and market data utilities for financial trading experiments.

This project is a research codebase for experimenting with portfolio allocation agents rather than a packaged library. It is useful for studying how actor-critic methods behave in a trading environment with transaction costs and historical market data.

## Highlights

- Custom TD3 implementation for continuous portfolio allocation
- Custom DDPG implementation
- EIIE-style portfolio model reference based on Jiang et al.
- Trading environment and wrapper modules
- Market data utilities for Yahoo Finance and Binance-style data workflows
- Replay buffer, noise, and exploration helpers for RL experiments

## Project Structure

```text
agent/          TD3, DDPG, and shared agent logic
data/           Data loading utilities
environment/    Trading environment and wrappers
networks/       Neural network models
utils/          Replay buffer, noise, and scheduling helpers
main.py         Example TD3 training entry point
```

## Installation

```bash
git clone https://github.com/novis10813/Portfolio-Optimizer.git
cd Portfolio-Optimizer
pip install -r requirements.txt
```

The original environment was developed around Python 3.7-3.9 era packages and PyTorch 1.11. If you are running on a newer Python or CUDA version, expect to adjust the pinned dependencies.

## Usage

`main.py` is the current example entry point. It builds a `TradingEnv`, wraps it, configures TD3 hyperparameters, and starts training.

```bash
python main.py
```

Before running, check the paths and hardware settings in `main.py`:

- `TradingEnv('data/history', ...)` expects historical data under `data/history`.
- `device` is set to `cuda` by default.
- Training length, replay buffer size, and exploration settings are configured in the `params` dictionary.

## Research Context

The implementation is inspired by portfolio management and continuous-control reinforcement learning papers:

1. Jiang et al., "A Deep Reinforcement Learning Framework for the Financial Portfolio Management Problem". [arXiv:1706.10059](https://arxiv.org/abs/1706.10059)
2. Fujimoto et al., "Addressing Function Approximation Error in Actor-Critic Methods". [arXiv:1802.09477](https://arxiv.org/abs/1802.09477)
3. Lillicrap et al., "Continuous Control with Deep Reinforcement Learning". [arXiv:1509.02971](https://arxiv.org/abs/1509.02971)

## Status

This is an experimental research repository. The code is best read as a portfolio RL prototype and reference implementation, not as production trading software.
