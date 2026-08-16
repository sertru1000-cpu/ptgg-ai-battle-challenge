# V17 MCTS vs V6-Greedy Divergence Analysis

Games: 14 | V17 losses: 11 | V17 wins: 3
Decisions where a real search ran: 393
Decisions where MCTS's final pick != V6's raw greedy pick ("diverged"): 192 (48.9% of searched decisions)

## Terminal-reward correlation (testing the mean-scaling hypothesis)

- Diverged decisions where at least one backing rollout hit a terminal (+-1,000,000) reward: 159/192 (82.8%)
- Non-diverged decisions where at least one backing rollout hit a terminal reward: 181/201 (90.0%)

If divergence is disproportionately associated with a terminal-reward hit, that directly supports the hypothesis that a single rare simulated conclusion (not a stable multi-sample signal) is what's flipping MCTS's pick away from the greedy choice.

## Top Divergence Patterns (MCTS override vs V6 greedy)

### MCTS:[PLAY] vs V6:[PLAY]
- Occurrences: 55 | In games V17 lost: 44 | Win rate when this diverged: 20.0%
- Of these, backed by a rollout that hit a terminal reward: 45/55 (81.8%)
  - game 1 decision 8 (turn 3, visits=61, hit_terminal=False): MCTS attackId=None cardId=None | V6 attackId=None cardId=None
  - game 1 decision 22 (turn 5, visits=56, hit_terminal=False): MCTS attackId=None cardId=None | V6 attackId=None cardId=None
  - game 1 decision 33 (turn 9, visits=57, hit_terminal=True): MCTS attackId=None cardId=None | V6 attackId=None cardId=None

### MCTS:[END] vs V6:[PLAY]
- Occurrences: 24 | In games V17 lost: 23 | Win rate when this diverged: 4.2%
- Of these, backed by a rollout that hit a terminal reward: 17/24 (70.8%)
  - game 1 decision 7 (turn 1, visits=112, hit_terminal=True): MCTS attackId=None cardId=None | V6 attackId=None cardId=None
  - game 1 decision 31 (turn 7, visits=55, hit_terminal=True): MCTS attackId=None cardId=None | V6 attackId=None cardId=None
  - game 3 decision 2 (turn 1, visits=79, hit_terminal=True): MCTS attackId=None cardId=None | V6 attackId=None cardId=None

### MCTS:[ATTACH] vs V6:[PLAY]
- Occurrences: 16 | In games V17 lost: 13 | Win rate when this diverged: 18.8%
- Of these, backed by a rollout that hit a terminal reward: 12/16 (75.0%)
  - game 1 decision 21 (turn 5, visits=57, hit_terminal=False): MCTS attackId=None cardId=None | V6 attackId=None cardId=None
  - game 3 decision 30 (turn 9, visits=89, hit_terminal=True): MCTS attackId=None cardId=None | V6 attackId=None cardId=None
  - game 4 decision 18 (turn 5, visits=91, hit_terminal=True): MCTS attackId=None cardId=None | V6 attackId=None cardId=None

### MCTS:[PLAY] vs V6:[EVOLVE]
- Occurrences: 9 | In games V17 lost: 3 | Win rate when this diverged: 66.7%
- Of these, backed by a rollout that hit a terminal reward: 8/9 (88.9%)
  - game 7 decision 8 (turn 3, visits=77, hit_terminal=True): MCTS attackId=None cardId=None | V6 attackId=None cardId=None
  - game 7 decision 15 (turn 5, visits=72, hit_terminal=True): MCTS attackId=None cardId=None | V6 attackId=None cardId=None
  - game 12 decision 16 (turn 7, visits=68, hit_terminal=True): MCTS attackId=None cardId=None | V6 attackId=None cardId=None

### MCTS:[EVOLVE] vs V6:[PLAY]
- Occurrences: 8 | In games V17 lost: 5 | Win rate when this diverged: 37.5%
- Of these, backed by a rollout that hit a terminal reward: 7/8 (87.5%)
  - game 1 decision 11 (turn 3, visits=59, hit_terminal=False): MCTS attackId=None cardId=None | V6 attackId=None cardId=None
  - game 3 decision 13 (turn 7, visits=58, hit_terminal=True): MCTS attackId=None cardId=None | V6 attackId=None cardId=None
  - game 11 decision 9 (turn 5, visits=62, hit_terminal=True): MCTS attackId=None cardId=None | V6 attackId=None cardId=None

### MCTS:[ATTACH] vs V6:[EVOLVE]
- Occurrences: 7 | In games V17 lost: 4 | Win rate when this diverged: 42.9%
- Of these, backed by a rollout that hit a terminal reward: 7/7 (100.0%)
  - game 1 decision 44 (turn 9, visits=54, hit_terminal=True): MCTS attackId=None cardId=None | V6 attackId=None cardId=None
  - game 2 decision 3 (turn 3, visits=133, hit_terminal=True): MCTS attackId=None cardId=None | V6 attackId=None cardId=None
  - game 7 decision 14 (turn 5, visits=72, hit_terminal=True): MCTS attackId=None cardId=None | V6 attackId=None cardId=None

### MCTS:[PLAY] vs V6:[ABILITY]
- Occurrences: 7 | In games V17 lost: 4 | Win rate when this diverged: 42.9%
- Of these, backed by a rollout that hit a terminal reward: 7/7 (100.0%)
  - game 2 decision 6 (turn 5, visits=93, hit_terminal=True): MCTS attackId=None cardId=None | V6 attackId=None cardId=None
  - game 13 decision 20 (turn 9, visits=56, hit_terminal=True): MCTS attackId=None cardId=None | V6 attackId=None cardId=None
  - game 13 decision 22 (turn 9, visits=51, hit_terminal=True): MCTS attackId=None cardId=None | V6 attackId=None cardId=None

### MCTS:[RETREAT] vs V6:[PLAY]
- Occurrences: 7 | In games V17 lost: 7 | Win rate when this diverged: 0.0%
- Of these, backed by a rollout that hit a terminal reward: 6/7 (85.7%)
  - game 1 decision 23 (turn 5, visits=55, hit_terminal=False): MCTS attackId=None cardId=None | V6 attackId=None cardId=None
  - game 4 decision 19 (turn 5, visits=100, hit_terminal=True): MCTS attackId=None cardId=None | V6 attackId=None cardId=None
  - game 4 decision 33 (turn 7, visits=69, hit_terminal=True): MCTS attackId=None cardId=None | V6 attackId=None cardId=None

### MCTS:[ABILITY] vs V6:[PLAY]
- Occurrences: 7 | In games V17 lost: 4 | Win rate when this diverged: 42.9%
- Of these, backed by a rollout that hit a terminal reward: 5/7 (71.4%)
  - game 3 decision 44 (turn 11, visits=57, hit_terminal=True): MCTS attackId=None cardId=None | V6 attackId=None cardId=None
  - game 11 decision 36 (turn 7, visits=50, hit_terminal=False): MCTS attackId=None cardId=None | V6 attackId=None cardId=None
  - game 13 decision 25 (turn 9, visits=55, hit_terminal=True): MCTS attackId=None cardId=None | V6 attackId=None cardId=None

### MCTS:[END] vs V6:[ATTACH]
- Occurrences: 6 | In games V17 lost: 4 | Win rate when this diverged: 33.3%
- Of these, backed by a rollout that hit a terminal reward: 4/6 (66.7%)
  - game 2 decision 2 (turn 1, visits=121, hit_terminal=True): MCTS attackId=None cardId=None | V6 attackId=None cardId=None
  - game 10 decision 3 (turn 1, visits=153, hit_terminal=True): MCTS attackId=None cardId=None | V6 attackId=None cardId=None
  - game 10 decision 4 (turn 3, visits=65, hit_terminal=False): MCTS attackId=None cardId=None | V6 attackId=None cardId=None

### MCTS:[PLAY] vs V6:[ATTACH]
- Occurrences: 6 | In games V17 lost: 5 | Win rate when this diverged: 16.7%
- Of these, backed by a rollout that hit a terminal reward: 6/6 (100.0%)
  - game 1 decision 3 (turn 1, visits=85, hit_terminal=True): MCTS attackId=None cardId=None | V6 attackId=None cardId=None
  - game 1 decision 5 (turn 1, visits=107, hit_terminal=True): MCTS attackId=None cardId=None | V6 attackId=None cardId=None
  - game 3 decision 7 (turn 5, visits=60, hit_terminal=True): MCTS attackId=None cardId=None | V6 attackId=None cardId=None

### MCTS:[ATTACH] vs V6:[ATTACH]
- Occurrences: 5 | In games V17 lost: 1 | Win rate when this diverged: 80.0%
- Of these, backed by a rollout that hit a terminal reward: 5/5 (100.0%)
  - game 11 decision 14 (turn 5, visits=62, hit_terminal=True): MCTS attackId=None cardId=None | V6 attackId=None cardId=None

### MCTS:[END] vs V6:[EVOLVE]
- Occurrences: 4 | In games V17 lost: 4 | Win rate when this diverged: 0.0%
- Of these, backed by a rollout that hit a terminal reward: 2/4 (50.0%)
  - game 2 decision 4 (turn 3, visits=126, hit_terminal=True): MCTS attackId=None cardId=None | V6 attackId=None cardId=None
  - game 3 decision 3 (turn 3, visits=67, hit_terminal=False): MCTS attackId=None cardId=None | V6 attackId=None cardId=None
  - game 9 decision 15 (turn 7, visits=62, hit_terminal=True): MCTS attackId=None cardId=None | V6 attackId=None cardId=None

### MCTS:[ATTACK] vs V6:[PLAY]
- Occurrences: 4 | In games V17 lost: 1 | Win rate when this diverged: 75.0%
- Of these, backed by a rollout that hit a terminal reward: 3/4 (75.0%)
  - game 4 decision 46 (turn 7, visits=53, hit_terminal=False): MCTS attackId=323 cardId=None | V6 attackId=None cardId=None

### MCTS:[END] vs V6:[ATTACK]
- Occurrences: 3 | In games V17 lost: 2 | Win rate when this diverged: 33.3%
- Of these, backed by a rollout that hit a terminal reward: 3/3 (100.0%)
  - game 11 decision 44 (turn 7, visits=49, hit_terminal=True): MCTS attackId=None cardId=None | V6 attackId=323 cardId=None
  - game 12 decision 12 (turn 3, visits=76, hit_terminal=True): MCTS attackId=None cardId=None | V6 attackId=323 cardId=None

## Raw Data

- Per-decision: `results\v17_divergence_PREFIX_unnormalized_value_bug\raw_decisions.jsonl`
- Per-game: `results\v17_divergence_PREFIX_unnormalized_value_bug\raw_games.jsonl`