# B1 P(win) training report

rows=341302, episodes=1000, features=87
valid AUC=0.8334  log_loss=0.5022  best_iteration=160

## AUC by turn bucket (valid)
- turns 0-2: AUC=0.6805 (n=10912)
- turns 3-5: AUC=0.7442 (n=16138)
- turns 6-9: AUC=0.8756 (n=21663)
- turns 10-14: AUC=0.9013 (n=14477)
- turns 15-99: AUC=0.9039 (n=3894)

## Calibration by predicted-probability decile (valid)
- decile 0: pred_mean=0.064 actual=0.046 n=6709
- decile 1: pred_mean=0.175 actual=0.145 n=6719
- decile 2: pred_mean=0.286 actual=0.249 n=6697
- decile 3: pred_mean=0.388 actual=0.353 n=6728
- decile 4: pred_mean=0.467 actual=0.440 n=6689
- decile 5: pred_mean=0.540 actual=0.545 n=6708
- decile 6: pred_mean=0.630 actual=0.687 n=6709
- decile 7: pred_mean=0.722 actual=0.769 n=6720
- decile 8: pred_mean=0.830 actual=0.826 n=6696
- decile 9: pred_mean=0.946 actual=0.942 n=6709

## Export parity: max |exported - xgboost| over 500 rows = 0.009295