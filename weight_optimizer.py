"""
Weight Optimizer Module
=======================
Sistema di ottimizzazione automatica dei pesi per il trading bot.

Metodi disponibili:
1. Grid Search - Testa tutte le combinazioni possibili (completo ma lento)
2. Random Search - Testa combinazioni casuali (veloce, buon compromesso)
3. Genetic Algorithm - Evoluzione naturale dei parametri (ottimale per spazi grandi)

Uso:
    from weight_optimizer import WeightOptimizer
    from backtester import Backtester, WeightsConfig

    bt = Backtester(symbols=['BTC', 'ETH'], days=30)
    bt.download_data()

    optimizer = WeightOptimizer(bt)
    best_config = optimizer.grid_search(...)
    # oppure
    best_config = optimizer.random_search(n_iterations=100)
    # oppure
    best_config = optimizer.genetic_algorithm(population_size=50, generations=20)
"""

import os
import json
import random
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Callable
from dataclasses import dataclass, field
import copy
import itertools

from backtester import Backtester, WeightsConfig, BacktestResult


@dataclass
class OptimizationResult:
    """Risultato dell'ottimizzazione."""
    best_config: WeightsConfig
    best_result: BacktestResult
    all_results: List[Tuple[WeightsConfig, BacktestResult]]
    method: str
    iterations: int
    duration_seconds: float
    parameter_space: Dict

    def to_dict(self) -> dict:
        return {
            'method': self.method,
            'iterations': self.iterations,
            'duration_seconds': round(self.duration_seconds, 2),
            'best_config': self.best_config.to_dict(),
            'best_metrics': self.best_result.to_dict(),
            'parameter_space': self.parameter_space,
        }

    def summary(self) -> str:
        """Genera un sommario testuale."""
        lines = [
            f"=== Optimization Results ({self.method}) ===",
            f"Iterations: {self.iterations}",
            f"Duration: {self.duration_seconds:.1f}s",
            f"",
            f"Best Configuration: {self.best_config.name}",
            f"  - Profit Factor: {self.best_result.profit_factor:.2f}",
            f"  - Win Rate: {self.best_result.win_rate*100:.1f}%",
            f"  - Total P&L: {self.best_result.total_pnl_pct:+.2f}%",
            f"  - Total Trades: {self.best_result.total_trades}",
        ]
        return "\n".join(lines)


class WeightOptimizer:
    """
    Ottimizzatore dei pesi per il trading bot.
    """

    # Parametri ottimizzabili con i loro range di default
    DEFAULT_PARAM_RANGES = {
        # Pesi BEARISH
        'weight_fear_greed_fear': (4.0, 15.0, 2.0),  # (min, max, step)
        'weight_rsi_overbought': (8.0, 20.0, 2.0),
        'weight_trend_bearish': (5.0, 15.0, 2.5),
        'weight_forecast_negative': (3.0, 12.0, 2.0),
        'weight_macd_negative': (2.0, 10.0, 2.0),

        # Pesi BULLISH
        'weight_fear_greed_greed': (4.0, 15.0, 2.0),
        'weight_rsi_oversold': (8.0, 20.0, 2.0),
        'weight_trend_bullish': (5.0, 15.0, 2.5),
        'weight_forecast_positive': (3.0, 12.0, 2.0),
        'weight_macd_positive': (2.0, 10.0, 2.0),

        # Soglie
        'score_threshold_open': (10.0, 25.0, 2.5),
        'score_threshold_strong': (20.0, 35.0, 5.0),

        # Trading params
        'take_profit_pct': (3.0, 10.0, 1.0),
        'stop_loss_pct': (5.0, 15.0, 2.0),
        'trailing_stop_pct': (4.0, 12.0, 2.0),
        'trailing_activation_pct': (2.0, 6.0, 1.0),
    }

    def __init__(
        self,
        backtester: Backtester,
        fitness_fn: Optional[Callable[[BacktestResult], float]] = None
    ):
        """
        Inizializza l'ottimizzatore.

        Args:
            backtester: Backtester già inizializzato con dati scaricati
            fitness_fn: Funzione per calcolare fitness (default: profit_factor * win_rate)
        """
        self.backtester = backtester
        self.fitness_fn = fitness_fn or self._default_fitness
        self._results_cache: Dict[str, BacktestResult] = {}

    def _default_fitness(self, result: BacktestResult) -> float:
        """
        Fitness di default: bilancia profit factor, win rate e numero trade.
        """
        if result.total_trades < 5:
            return 0.0  # Troppo pochi trade per essere significativo

        # Profit factor (capped a 5 per evitare overfitting)
        pf = min(result.profit_factor, 5.0)

        # Win rate
        wr = result.win_rate

        # Penalizza configurazioni con pochissimi trade
        trade_factor = min(result.total_trades / 20, 1.0)

        # Fitness composita
        return pf * wr * trade_factor

    def _config_hash(self, config: WeightsConfig) -> str:
        """Genera un hash unico per la configurazione."""
        return json.dumps(config.to_dict(), sort_keys=True)

    def _evaluate(self, config: WeightsConfig, verbose: bool = False) -> BacktestResult:
        """Valuta una configurazione (con caching)."""
        config_hash = self._config_hash(config)

        if config_hash in self._results_cache:
            return self._results_cache[config_hash]

        result = self.backtester.run(config, verbose=verbose)
        self._results_cache[config_hash] = result
        return result

    def grid_search(
        self,
        param_ranges: Optional[Dict] = None,
        base_config: Optional[WeightsConfig] = None,
        max_combinations: int = 1000,
        verbose: bool = True
    ) -> OptimizationResult:
        """
        Ottimizzazione tramite grid search.

        Testa tutte le combinazioni di parametri nei range specificati.

        Args:
            param_ranges: Dict con {param_name: (min, max, step)}
                          Se None, usa solo i parametri più importanti
            base_config: Configurazione base da modificare
            max_combinations: Limite massimo di combinazioni da testare
            verbose: Se stampare progressi

        Returns:
            OptimizationResult con la migliore configurazione
        """
        start_time = datetime.now()
        base = base_config or WeightsConfig.from_env()

        # Usa parametri più importanti se non specificati
        if param_ranges is None:
            param_ranges = {
                'weight_rsi_overbought': (10.0, 20.0, 5.0),
                'weight_rsi_oversold': (10.0, 20.0, 5.0),
                'score_threshold_open': (12.0, 20.0, 4.0),
                'take_profit_pct': (3.0, 8.0, 2.5),
                'stop_loss_pct': (8.0, 12.0, 2.0),
            }

        # Genera tutte le combinazioni
        param_names = list(param_ranges.keys())
        param_values = []

        for name in param_names:
            min_val, max_val, step = param_ranges[name]
            values = []
            v = min_val
            while v <= max_val:
                values.append(v)
                v += step
            param_values.append(values)

        all_combinations = list(itertools.product(*param_values))

        # Limita combinazioni se troppe
        if len(all_combinations) > max_combinations:
            if verbose:
                print(f"Too many combinations ({len(all_combinations)}), sampling {max_combinations}")
            random.shuffle(all_combinations)
            all_combinations = all_combinations[:max_combinations]

        if verbose:
            print(f"Grid Search: testing {len(all_combinations)} combinations")
            print(f"Parameters: {param_names}")

        all_results = []
        best_fitness = -float('inf')
        best_config = None
        best_result = None

        for i, combo in enumerate(all_combinations):
            # Crea configurazione
            config_dict = {name: val for name, val in zip(param_names, combo)}
            config = copy.deepcopy(base)
            config.name = f"grid_{i+1}"

            for name, val in config_dict.items():
                setattr(config, name, val)

            # Valuta
            result = self._evaluate(config)
            fitness = self.fitness_fn(result)
            all_results.append((config, result))

            if fitness > best_fitness:
                best_fitness = fitness
                best_config = config
                best_result = result

            if verbose and (i + 1) % 10 == 0:
                print(f"  [{i+1}/{len(all_combinations)}] Best PF: {best_result.profit_factor:.2f}, "
                      f"WR: {best_result.win_rate*100:.1f}%")

        duration = (datetime.now() - start_time).total_seconds()

        # Rinomina best config
        best_config.name = "grid_best"

        return OptimizationResult(
            best_config=best_config,
            best_result=best_result,
            all_results=all_results,
            method="grid_search",
            iterations=len(all_combinations),
            duration_seconds=duration,
            parameter_space=param_ranges
        )

    def random_search(
        self,
        n_iterations: int = 100,
        param_ranges: Optional[Dict] = None,
        base_config: Optional[WeightsConfig] = None,
        verbose: bool = True
    ) -> OptimizationResult:
        """
        Ottimizzazione tramite random search.

        Più efficiente di grid search per spazi grandi.

        Args:
            n_iterations: Numero di configurazioni casuali da testare
            param_ranges: Dict con {param_name: (min, max)}
            base_config: Configurazione base
            verbose: Se stampare progressi

        Returns:
            OptimizationResult
        """
        start_time = datetime.now()
        base = base_config or WeightsConfig.from_env()

        if param_ranges is None:
            param_ranges = {name: (r[0], r[1]) for name, r in self.DEFAULT_PARAM_RANGES.items()}

        if verbose:
            print(f"Random Search: {n_iterations} iterations")
            print(f"Parameters: {list(param_ranges.keys())}")

        all_results = []
        best_fitness = -float('inf')
        best_config = None
        best_result = None

        for i in range(n_iterations):
            # Crea configurazione casuale
            config = copy.deepcopy(base)
            config.name = f"random_{i+1}"

            for name, (min_val, max_val) in param_ranges.items():
                random_val = random.uniform(min_val, max_val)
                # Arrotonda a 1 decimale
                random_val = round(random_val, 1)
                setattr(config, name, random_val)

            # Valuta
            result = self._evaluate(config)
            fitness = self.fitness_fn(result)
            all_results.append((config, result))

            if fitness > best_fitness:
                best_fitness = fitness
                best_config = config
                best_result = result

            if verbose and (i + 1) % 20 == 0:
                print(f"  [{i+1}/{n_iterations}] Best PF: {best_result.profit_factor:.2f}, "
                      f"WR: {best_result.win_rate*100:.1f}%")

        duration = (datetime.now() - start_time).total_seconds()
        best_config.name = "random_best"

        return OptimizationResult(
            best_config=best_config,
            best_result=best_result,
            all_results=all_results,
            method="random_search",
            iterations=n_iterations,
            duration_seconds=duration,
            parameter_space=param_ranges
        )

    def genetic_algorithm(
        self,
        population_size: int = 50,
        generations: int = 20,
        mutation_rate: float = 0.2,
        crossover_rate: float = 0.7,
        elite_size: int = 5,
        param_ranges: Optional[Dict] = None,
        base_config: Optional[WeightsConfig] = None,
        verbose: bool = True
    ) -> OptimizationResult:
        """
        Ottimizzazione tramite algoritmo genetico.

        Simula l'evoluzione naturale per trovare i parametri ottimali.

        Args:
            population_size: Dimensione della popolazione
            generations: Numero di generazioni
            mutation_rate: Probabilità di mutazione (0-1)
            crossover_rate: Probabilità di crossover (0-1)
            elite_size: Numero di individui migliori da preservare
            param_ranges: Dict con {param_name: (min, max)}
            base_config: Configurazione base
            verbose: Se stampare progressi

        Returns:
            OptimizationResult
        """
        start_time = datetime.now()
        base = base_config or WeightsConfig.from_env()

        if param_ranges is None:
            param_ranges = {name: (r[0], r[1]) for name, r in self.DEFAULT_PARAM_RANGES.items()}

        param_names = list(param_ranges.keys())

        if verbose:
            print(f"Genetic Algorithm: pop={population_size}, gen={generations}")
            print(f"Parameters ({len(param_names)}): {param_names[:5]}...")

        def create_individual() -> WeightsConfig:
            """Crea un individuo casuale."""
            config = copy.deepcopy(base)
            for name, (min_val, max_val) in param_ranges.items():
                setattr(config, name, round(random.uniform(min_val, max_val), 1))
            return config

        def mutate(config: WeightsConfig) -> WeightsConfig:
            """Applica mutazione casuale."""
            new_config = copy.deepcopy(config)
            for name in param_names:
                if random.random() < mutation_rate:
                    min_val, max_val = param_ranges[name]
                    current = getattr(new_config, name)
                    # Mutazione gaussiana
                    delta = (max_val - min_val) * 0.2 * random.gauss(0, 1)
                    new_val = max(min_val, min(max_val, current + delta))
                    setattr(new_config, name, round(new_val, 1))
            return new_config

        def crossover(parent1: WeightsConfig, parent2: WeightsConfig) -> WeightsConfig:
            """Crossover tra due genitori."""
            child = copy.deepcopy(parent1)
            for name in param_names:
                if random.random() < 0.5:
                    setattr(child, name, getattr(parent2, name))
            return child

        # Inizializza popolazione
        population = [create_individual() for _ in range(population_size)]
        all_results = []
        best_ever_fitness = -float('inf')
        best_ever_config = None
        best_ever_result = None

        for gen in range(generations):
            # Valuta fitness di tutti
            fitness_scores = []
            for config in population:
                result = self._evaluate(config)
                fitness = self.fitness_fn(result)
                fitness_scores.append((config, result, fitness))
                all_results.append((config, result))

                if fitness > best_ever_fitness:
                    best_ever_fitness = fitness
                    best_ever_config = copy.deepcopy(config)
                    best_ever_result = result

            # Ordina per fitness
            fitness_scores.sort(key=lambda x: x[2], reverse=True)

            if verbose:
                best_gen = fitness_scores[0]
                print(f"  Gen {gen+1}/{generations}: Best PF={best_gen[1].profit_factor:.2f}, "
                      f"WR={best_gen[1].win_rate*100:.1f}%, "
                      f"Ever PF={best_ever_result.profit_factor:.2f}")

            # Elite (sopravvivono automaticamente)
            new_population = [config for config, _, _ in fitness_scores[:elite_size]]

            # Selezione e riproduzione
            while len(new_population) < population_size:
                # Tournament selection
                tournament_size = 3
                tournament = random.sample(fitness_scores, tournament_size)
                tournament.sort(key=lambda x: x[2], reverse=True)
                parent1 = tournament[0][0]

                tournament = random.sample(fitness_scores, tournament_size)
                tournament.sort(key=lambda x: x[2], reverse=True)
                parent2 = tournament[0][0]

                # Crossover
                if random.random() < crossover_rate:
                    child = crossover(parent1, parent2)
                else:
                    child = copy.deepcopy(parent1)

                # Mutazione
                child = mutate(child)
                new_population.append(child)

            population = new_population

        duration = (datetime.now() - start_time).total_seconds()
        best_ever_config.name = "genetic_best"

        return OptimizationResult(
            best_config=best_ever_config,
            best_result=best_ever_result,
            all_results=all_results,
            method="genetic_algorithm",
            iterations=population_size * generations,
            duration_seconds=duration,
            parameter_space=param_ranges
        )

    def quick_optimize(
        self,
        method: str = 'random',
        verbose: bool = True
    ) -> OptimizationResult:
        """
        Ottimizzazione rapida con parametri di default.

        Args:
            method: 'grid', 'random', o 'genetic'
            verbose: Se stampare progressi

        Returns:
            OptimizationResult
        """
        if method == 'grid':
            return self.grid_search(verbose=verbose)
        elif method == 'genetic':
            return self.genetic_algorithm(
                population_size=30,
                generations=10,
                verbose=verbose
            )
        else:  # random
            return self.random_search(
                n_iterations=50,
                verbose=verbose
            )

    def generate_report(self, opt_result: OptimizationResult) -> str:
        """Genera un report markdown dell'ottimizzazione."""
        best = opt_result.best_result
        config = opt_result.best_config

        lines = [
            "# Weight Optimization Report",
            f"\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"\n## Method: {opt_result.method}",
            f"- Iterations: {opt_result.iterations}",
            f"- Duration: {opt_result.duration_seconds:.1f}s",
            f"\n## Best Configuration: {config.name}",
            f"\n### Performance Metrics",
            f"- **Profit Factor**: {best.profit_factor:.2f}",
            f"- **Win Rate**: {best.win_rate*100:.1f}%",
            f"- **Total P&L**: {best.total_pnl_pct:+.2f}%",
            f"- **Total Trades**: {best.total_trades}",
            f"- **Avg Win**: {best.avg_win_pct:+.2f}%",
            f"- **Avg Loss**: {best.avg_loss_pct:.2f}%",
            f"\n### Optimized Weights",
            "```",
            f"# BEARISH weights",
            f"WEIGHT_FEAR_GREED_FEAR={config.weight_fear_greed_fear}",
            f"WEIGHT_RSI_OVERBOUGHT={config.weight_rsi_overbought}",
            f"WEIGHT_TREND_BEARISH={config.weight_trend_bearish}",
            f"WEIGHT_FORECAST_NEGATIVE={config.weight_forecast_negative}",
            f"WEIGHT_MACD_NEGATIVE={config.weight_macd_negative}",
            f"",
            f"# BULLISH weights",
            f"WEIGHT_FEAR_GREED_GREED={config.weight_fear_greed_greed}",
            f"WEIGHT_RSI_OVERSOLD={config.weight_rsi_oversold}",
            f"WEIGHT_TREND_BULLISH={config.weight_trend_bullish}",
            f"WEIGHT_FORECAST_POSITIVE={config.weight_forecast_positive}",
            f"WEIGHT_MACD_POSITIVE={config.weight_macd_positive}",
            f"",
            f"# Thresholds",
            f"SCORE_THRESHOLD_OPEN={config.score_threshold_open}",
            f"SCORE_THRESHOLD_STRONG={config.score_threshold_strong}",
            f"",
            f"# Trading params",
            f"TAKE_PROFIT_PERCENT={config.take_profit_pct}",
            f"INITIAL_STOP_LOSS_PERCENT={config.stop_loss_pct}",
            f"TRAILING_STOP_PERCENT={config.trailing_stop_pct}",
            f"TRAILING_STOP_ACTIVATION_PERCENT={config.trailing_activation_pct}",
            "```",
            f"\n### Exit Reasons",
        ]

        for reason, count in best.exit_reasons.items():
            pct = (count / best.total_trades * 100) if best.total_trades > 0 else 0
            lines.append(f"- {reason}: {count} ({pct:.1f}%)")

        # Top 5 configurations
        if len(opt_result.all_results) > 1:
            lines.append("\n## Top 5 Configurations")
            lines.append("\n| Rank | Config | Profit Factor | Win Rate | P&L |")
            lines.append("|------|--------|---------------|----------|-----|")

            # Sort by fitness
            sorted_results = sorted(
                opt_result.all_results,
                key=lambda x: self.fitness_fn(x[1]),
                reverse=True
            )[:5]

            for i, (cfg, res) in enumerate(sorted_results):
                lines.append(
                    f"| {i+1} | {cfg.name} | {res.profit_factor:.2f} | "
                    f"{res.win_rate*100:.1f}% | {res.total_pnl_pct:+.2f}% |"
                )

        return "\n".join(lines)


# Esempio di utilizzo
if __name__ == "__main__":
    print("Weight Optimizer - Example Usage")
    print("=" * 50)

    # Inizializza backtester
    bt = Backtester(symbols=['BTC', 'ETH'], days=30, interval='1h')

    if bt.download_data():
        # Inizializza optimizer
        optimizer = WeightOptimizer(bt)

        # Test rapido con random search
        print("\n--- Running Random Search ---")
        result = optimizer.random_search(n_iterations=30, verbose=True)

        print("\n" + result.summary())

        # Genera report
        report = optimizer.generate_report(result)

        with open('optimization_report.md', 'w') as f:
            f.write(report)

        print(f"\nReport saved to optimization_report.md")

        # Suggerimento per .env
        print("\n--- Suggested .env values ---")
        cfg = result.best_config
        print(f"WEIGHT_RSI_OVERBOUGHT={cfg.weight_rsi_overbought}")
        print(f"WEIGHT_RSI_OVERSOLD={cfg.weight_rsi_oversold}")
        print(f"SCORE_THRESHOLD_OPEN={cfg.score_threshold_open}")
        print(f"TAKE_PROFIT_PERCENT={cfg.take_profit_pct}")
        print(f"INITIAL_STOP_LOSS_PERCENT={cfg.stop_loss_pct}")
    else:
        print("Failed to download data")
