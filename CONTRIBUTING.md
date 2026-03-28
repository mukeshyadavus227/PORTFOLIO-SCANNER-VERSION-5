 e.g., `entryPrice`, `regimeScore`
 - **Constants:** Use `UPPER_SNAKE_CASE` — e.g., `MAX_LOOKBACK`, `DEFAULT_THRESHOLD`
 - **Functions:** Use `camelCase` with descriptive verbs — e.g., `calculateScore()`, `detectRegime()`
 - **Strategy prefixes:** All sub-strategy variables must include their ID prefix — e.g., `s1_signal`, `s2_entryCondition`

 ### Code Organization

 - Each file should have a header comment block describing its purpose, inputs, and outputs.
 - Group related logic into clearly labeled sections using Pine Script comment blocks.
 - Keep functions focused — each function should do one thing well.
 - Avoid magic numbers; define them as named constants in `src/utils/constants.pine`.

 ### Documentation

 - Every public function must have a comment describing parameters and return values.
 - Complex logic should include inline comments explaining the reasoning.
 - Update the relevant `docs/` file when making architectural changes.

 ---

 ## Strategy Proposal Process

 To propose a new sub-strategy:

 1. Open an issue using the "Strategy Proposal" template.
 2. Include: hypothesis, entry/exit logic, target regime, expected edge, and preliminary backtest results.
 3. Discuss with maintainers before implementing.
 4. Once approved, implement following the standardized sub-strategy interface.

 ---

 ## Commit Messages

 Use clear, descriptive commit messages:

 ```
 <type>(<scope>): <description>

 Types: feat, fix, docs, refactor, test, chore
 Scope: S1, S2, S3, S4, regime, scoring, fire, utils, config, docs

 Examples:
 feat(S1): add momentum crossover entry logic
 fix(regime): correct volatility threshold for range detection
 docs(scoring): update scoring methodology documentation
 test(S2): add backtest results for BTC 4H timeframe
 ```

 ---

 ## Pull Request Guidelines

 - Reference any related issues.
 - Include backtest results if modifying strategy logic.
 - Ensure all existing tests still pass.
 - Update documentation as needed.
 - Keep PRs focused — one feature or fix per PR.