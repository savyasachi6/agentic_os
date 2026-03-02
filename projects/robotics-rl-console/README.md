# Robotics & RL Console

An interface for integrating Agent OS with robotics frameworks (ROS 2) and Reinforcement Learning environments.

## Purpose

The `robotics-rl-console` provides the high-level reasoning bridge for physical and simulated agents. It allows the Agent OS to act as the "Cognitive Layer" while low-level control loops handle motor commands and sensor fusion.

## Key Features

- **ROS 2 Bridge**: Maps agent tool calls to ROS 2 topics and services.
- **Reward Shaper**: Uses the `agentos_skills/reward-shaper` skill to dynamically define and evaluate reinforcement learning reward functions.
- **Telemetry Dashboard**: Real-time visualization of robot state, joint positions, and sensor streams.
- **Simulation Sync**: Manages the lifecycle of Gazebo or Isaac Sim environments for agent training and verification.

## Usage

```bash
python main.py --project robotics-rl-console --ros-domain 42
```
