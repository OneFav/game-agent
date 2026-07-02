# Regression Notes

- Infeasible trials are dominated by collision events when `risk_margin` is too low or spacing is too aggressive.
- The promoted config increases `risk_margin` to 1.2 while keeping `desired_speed` at 5.5, which preserves throughput and removes collisions on the chosen seeds.