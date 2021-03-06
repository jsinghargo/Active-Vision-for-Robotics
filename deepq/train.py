import argparse
import os
import gym
import kuka

from baselines import deepq
import tensorboard_logger as tbl

def main():
  parser = argparse.ArgumentParser(description='DQN for Active Vision')
  parser.add_argument('--commit', type=str, help='commit SHA of this run')
  parser.add_argument('--exp-name', type=str, default=None,
    help='name of experiment. data will be saved to folder of same name')
  parser.add_argument('--render', type=bool, nargs='?', const=True,
    help='whether to render GUI or not')
  parser.add_argument('--max-episodes', type=int, help='maximum episodes')
  parser.add_argument('--checkpoint-freq', type=int, default=None,
    help='save model after every this many episodes')
  args = parser.parse_args()

  print('This run is based upon #commit {}'.format(args.commit))
  if args.exp_name is not None:
    exp_dir = os.path.join('exp/deepq', args.exp_name)
    if not os.path.exists(exp_dir): os.makedirs(exp_dir)
    models_dir = os.path.join(exp_dir, 'models')
    if not os.path.exists(models_dir): os.makedirs(models_dir)

  env = gym.make("kuka-v0")
  env.init_bullet(render=args.render, delta=1.0)

  # Configure tensorboard logger
  tb_dir = os.path.join(exp_dir, 'tb')
  tbl.configure(tb_dir)

  num_episode = 0
  def callback(lcl, _glb):
    nonlocal num_episode
    # Do stuff only when an episode is complete
    curr_episode = len(lcl['episode_rewards'])
    if curr_episode > num_episode:
      num_episode = curr_episode
      if num_episode > 1:
        prev_100_rewards = lcl['episode_rewards'][-101:-1]
        tbl.log_value('ep_reward', prev_100_rewards[-1], num_episode)
        tbl.log_value('mean_reward',
          sum(prev_100_rewards)/len(prev_100_rewards), num_episode)
      if num_episode % args.checkpoint_freq == 0:
        ckpt_file = os.path.join(models_dir, 'ckpt_{}.pkl'.format(num_episode))
        print('Saving model for episode {} to {} ...'.format(
          num_episode, ckpt_file))
        lcl['act'].save(ckpt_file)
      if num_episode == args.max_episodes:
        return True

    return False

  model = deepq.models.mlp([20])
  act = deepq.learn(
    env,
    q_func=model,
    lr=1e-3,
    buffer_size=50000,
    exploration_fraction=0.1,
    exploration_final_eps=0.02,
    print_freq=1,
    callback=callback
  )
  final_model_dir = os.path.join(exp_dir, "kuka_model.pkl")
  print("Saving model to {}".format(final_model_dir))
  act.save(final_model_dir)


if __name__ == '__main__':
  main()