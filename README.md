# Portfolio Scanner Version 5

> A multi-strategy Pine Script trading system featuring 4 sub-strategies (S1–S4), regime detection, dynamic scoring, winner selection, and composite fire conditions for TradingView.

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Sub-Strategies](#sub-strategies)
- [Modules](#modules)
- [Repository Structure](#repository-structure)
- [Getting Started](#getting-started)
- [Development Workflow](#development-workflow)
- [Testing](#testing)
- [Contributing](#contributing)
- [License](#license)

---

## Overview

Portfolio Scanner V5 is a comprehensive Pine Script strategy designed for TradingView. It combines multiple independent sub-strategies under a unified framework that includes market regime detection, dynamic strategy scoring, automatic winner selection, and composite fire conditions to generate high-confidence trade signals.

### Key Features

- **4 Independent Sub-Strategies (S1–S4):** Each sub-strategy implements a distinct trading logic and can operate standalone or as part of the ensemble.
- **Regime Detection:** Classifies the current market environment (trending, ranging, volatile, etc.) to adapt strategy behavior dynamically.
- **Dynamic Scoring Engine:** Scores each sub-strategy in real-time based on recent performance, win rate, and regime alignment.
- **Winner Selection:** Automatically selects the highest-scoring sub-strategy (or combination) for signal generation.
- **Composite Fire Conditions:** Aggregates signals from multiple modules with configurable confirmation logic before triggering entries/exits.

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                  PORTFOLIO SCANNER V5                │
├─────────────────────────────────────────────────────┤
│                                                     │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐         │
│  │ Market   │  │ Regime   │  │ Scoring  │         │
│  │ Data     │──│ Detector │──│ Engine   │         │
│  │ Input    │  │          │  │          │         │
│  └──────────┘  └──────────┘  └────┬─────┘         │
│                                    │                │
│  ┌────────┐ ┌────────┐ ┌────────┐ │ ┌────────┐   │
│  │  S1    │ │  S2    │ │  S3    │ │ │  S4    │   │
│  │Strategy│ │Strategy│ │Strategy│ │ │Strategy│   │
│  └───┬────┘ └───┬────┘ └───┬────┘ │ └───┬────┘   │
│      │          │          │      │     │         │
│      └──────────┴──────────┴──────┴─────┘         │
│                      │                             │
│              ┌───────┴───────┐                     │
│              │    Winner     │                     │
│              │   Selection   │                     │
│              └───────┬───────┘                     │
│                      │                             │
│              ┌───────┴───────┐                     │
│              │   Composite   │                     │
│              │     Fire      │                     │
│              │  Conditions   │                     │
│              └───────┬───────┘                     │
│                      │                             │
│              ┌───────┴───────┐                     │
│              │ Trade Signal  │                     │
│              │   Output      │                     │
│              └───────────────┘                     │
│                                                     │
└─────────────────────────────────────────────────────┘
```

---

## Sub-Strategies

| ID | Name | Description | File |
|----|------|-------------|------|
| S1 | Sub-Strategy 1 | *(Define logic here)* | `src/strategies/S1_strategy.pine` |
| S2 | Sub-Strategy 2 | *(Define logic here)* | `src/strategies/S2_strategy.pine` |
| S3 | Sub-Strategy 3 | *(Define logic here)* | `src/strategies/S3_strategy.pine` |
| S4 | Sub-Strategy 4 | *(Define logic here)* | `src/strategies/S4_strategy.pine` |

Each sub-strategy follows a standardized interface:
- Accepts market data and regime context as inputs
- Outputs a signal object with direction, confidence score, and metadata
- Can be independently backtested and validated

---

## Modules

### Regime Detection (`src/modules/regime_detection.pine`)
Classifies current market conditions into defined regimes (e.g., Bull Trend, Bear Trend, Range-Bound, High Volatility). Uses a combination of trend indicators, volatility measures, and market structure analysis.

### Scoring Engine (`src/modules/scoring_engine.pine`)
Evaluates each sub-strategy's recent performance within the current regime. Maintains rolling statistics and produces normalized scores used for winner selection.

### Winner Selection (`src/modules/winner_selection.pine`)
Takes scored outputs from all sub-strategies and selects the best-performing strategy (or weighted combination) for signal generation. Supports single-winner and blended-winner modes.

### Composite Fire Conditions (`src/modules/composite_fire.pine`)
Applies final confirmation filters before trade execution. Checks for alignment across multiple timeframes, volume confirmation, regime compatibility, and risk parameters before allowing a signal to "fire."

### Utilities (`src/utils/`)
Common helper functions: math operations, array utilities, string formatting, plotting helpers, and alert message builders.

---

## Repository Structure

```
PORTFOLIO-SCANNER-VERSION-5/
│
├── README.md                          # This file
├── SECURITY.md                        # Security policy
├── CONTRIBUTING.md                    # Contribution guidelines
├── CHANGELOG.md                       # Version history
├── .gitignore                         # Git ignore rules
│
├── .github/
│   ├── dependabot.yml                 # Dependabot configuration
│   ├── ISSUE_TEMPLATE/
│   │   ├── bug_report.md              # Bug report template
│   │   ├── feature_request.md         # Feature request template
│   │   └── strategy_proposal.md       # New strategy proposal
│   └── PULL_REQUEST_TEMPLATE.md       # PR template
│
├── src/
│   ├── main.pine                      # Main entry point - master strategy script
│   │
│   ├── strategies/
│   │   ├── S1_strategy.pine           # Sub-Strategy 1
│   │   ├── S2_strategy.pine           # Sub-Strategy 2
│   │   ├── S3_strategy.pine           # Sub-Strategy 3
│   │   └── S4_strategy.pine           # Sub-Strategy 4
│   │
│   ├── modules/
│   │   ├── regime_detection.pine      # Market regime classifier
│   │   ├── scoring_engine.pine        # Strategy scoring system
│   │   ├── winner_selection.pine      # Winner selection logic
│   │   └── composite_fire.pine        # Composite fire conditions
│   │
│   └── utils/
│       ├── helpers.pine               # Common utility functions
│       └── constants.pine             # Global constants and settings
│
├── config/
│   ├── default_settings.json          # Default strategy parameters
│   └── backtest_config.json           # Backtesting configuration
│
├── docs/
│   ├── ARCHITECTURE.md                # Detailed architecture documentation
│   ├── STRATEGY_GUIDE.md              # Guide for developing sub-strategies
│   ├── REGIME_DETECTION.md            # Regime detection methodology
│   ├── SCORING_METHODOLOGY.md         # Scoring engine documentation
│   └── DEPLOYMENT.md                  # TradingView deployment guide
│
├── tests/
│   ├── README.md                      # Testing guidelines
│   ├── backtest_results/              # Historical backtest outputs
│   └── validation/                    # Strategy validation scripts
│
└── research/
    ├── README.md                      # Research notes index
        ├── ideas/                         # Strategy ideas and hypotheses
            └── analysis/                      # Market analysis and findings
            ```

            ---

            ## Getting Started

            ### Prerequisites

            - A TradingView account (Pro, Pro+, or Premium recommended for multi-timeframe access)
            - Basic knowledge of Pine Script v5+
            - Git for version control

            ### Installation

            1. Clone this repository:
               ```bash
                  git clone https://github.com/mukeshyadavus227/PORTFOLIO-SCANNER-VERSION-5.git
                     cd PORTFOLIO-SCANNER-VERSION-5
                        ```

                        2. Open `src/main.pine` in TradingView's Pine Script Editor.

                        3. Adjust parameters in the strategy settings panel.

                        4. Apply the strategy to your desired chart and timeframe.

                        ---

                        ## Development Workflow

                        1. **Branch from main:** Create a feature branch for any changes.
                        2. **Develop:** Write or modify strategy code in `src/`.
                        3. **Document:** Update relevant docs in `docs/`.
                        4. **Test:** Run backtests and document results in `tests/backtest_results/`.
                        5. **Review:** Submit a Pull Request using the provided template.
                        6. **Merge:** After review and approval, merge to main.

                        ---

                        ## Testing

                        All strategies should be validated through:
                        - **Backtesting** across multiple timeframes and instruments
                        - **Walk-forward analysis** to test out-of-sample performance
                        - **Regime-specific testing** to ensure strategies perform as expected in their target regime
                        - **Parameter sensitivity analysis** to identify robust parameter ranges

                        Results should be documented in `tests/backtest_results/` with standardized reporting format.

                        ---

                        ## Contributing

                        Please read [CONTRIBUTING.md](CONTRIBUTING.md) for details on our development process, coding standards, and how to submit pull requests.

                        ---

                        ## License

                        This project is private and proprietary. All rights reserved.