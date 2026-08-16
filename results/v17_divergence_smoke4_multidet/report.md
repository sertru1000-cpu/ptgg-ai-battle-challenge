# V17 MCTS vs V6-Greedy Divergence Analysis

Games: 4 | V17 losses: 3 | V17 wins: 1
Decisions where a real search ran: 118
Decisions where MCTS's final pick != V6's raw greedy pick ("diverged"): 9 (7.6% of searched decisions)

## Terminal-reward correlation (testing the mean-scaling hypothesis)

- Diverged decisions where at least one backing rollout hit a terminal (+-1,000,000) reward: 1/9 (11.1%)
- Non-diverged decisions where at least one backing rollout hit a terminal reward: 42/109 (38.5%)

If divergence is disproportionately associated with a terminal-reward hit, that directly supports the hypothesis that a single rare simulated conclusion (not a stable multi-sample signal) is what's flipping MCTS's pick away from the greedy choice.

## Top Divergence Patterns (MCTS override vs V6 greedy)

### MCTS:[ATTACH] vs V6:[ATTACH]
- Occurrences: 2 | In games V17 lost: 1 | Win rate when this diverged: 50.0%
- Of these, backed by a rollout that hit a terminal reward: 0/2 (0.0%)
  - game 1 decision 8 (turn 1, visits=193, hit_terminal=False): MCTS played Basic {R} Energy (attackId=None) | V6 would have played Basic {R} Energy (attackId=None)

### MCTS:[PLAY] vs V6:[PLAY]
- Occurrences: 2 | In games V17 lost: 1 | Win rate when this diverged: 50.0%
- Of these, backed by a rollout that hit a terminal reward: 0/2 (0.0%)
  - game 3 decision 14 (turn 4, visits=188, hit_terminal=False): MCTS played Brock’s Scouting (attackId=None) | V6 would have played Crushing Hammer (attackId=None)

### MCTS:[EVOLVE] vs V6:[EVOLVE]
- Occurrences: 1 | In games V17 lost: 0 | Win rate when this diverged: 100.0%
- Of these, backed by a rollout that hit a terminal reward: 0/1 (0.0%)

### MCTS:[PLAY] vs V6:[ABILITY]
- Occurrences: 1 | In games V17 lost: 0 | Win rate when this diverged: 100.0%
- Of these, backed by a rollout that hit a terminal reward: 0/1 (0.0%)

### MCTS:[EVOLVE] vs V6:[PLAY]
- Occurrences: 1 | In games V17 lost: 1 | Win rate when this diverged: 0.0%
- Of these, backed by a rollout that hit a terminal reward: 0/1 (0.0%)
  - game 3 decision 13 (turn 4, visits=186, hit_terminal=False): MCTS played Drakloak (attackId=None) | V6 would have played Crushing Hammer (attackId=None)

### MCTS:[ATTACK] vs V6:[PLAY]
- Occurrences: 1 | In games V17 lost: 1 | Win rate when this diverged: 0.0%
- Of these, backed by a rollout that hit a terminal reward: 0/1 (0.0%)
  - game 3 decision 18 (turn 4, visits=178, hit_terminal=False): MCTS played None (attackId=323) | V6 would have played Dreepy (attackId=None)

### MCTS:[PLAY] vs V6:[EVOLVE]
- Occurrences: 1 | In games V17 lost: 1 | Win rate when this diverged: 0.0%
- Of these, backed by a rollout that hit a terminal reward: 1/1 (100.0%)
  - game 3 decision 57 (turn 12, visits=132, hit_terminal=True): MCTS played Lillie's Determination (attackId=None) | V6 would have played Drakloak (attackId=None)

## PLAY-vs-EVOLVE Card Tally (which card MCTS chose to play instead of evolving)

### Cards played in games V17 LOST

- Lillie's Determination: 1

### Cards played in games V17 WON

- (none)

## Raw Data

- Per-decision: `results\v17_divergence\raw_decisions.jsonl`
- Per-game: `results\v17_divergence\raw_games.jsonl`