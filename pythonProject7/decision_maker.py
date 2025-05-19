import numpy as np
from data_parser import InputData
from typing import Dict


class DecisionMaker:
    def __init__(self, data: InputData):
        self.data = data
        self.results = {}

    def calculate(self) -> Dict[str, any]:
        # 1. Нормализация оценок
        normalized = self._normalize_ratings()

        # 2. Автоматический расчет равных весов для экспертов
        expert_weights = self._calculate_expert_weights()

        # 3. Расчет агрегированных оценок с учетом весов экспертов
        aggregated = self._aggregate_ratings(normalized, expert_weights)

        # 4. Расчет итоговых оценок с весами критериев
        final_scores = self._calculate_final_scores(aggregated)

        # 5. Сортировка результатов
        sorted_scores = sorted(
            final_scores.items(),
            key=lambda x: x[1],
            reverse=True
        )

        self.results = {
            'expert_weights': expert_weights,
            'criteria_weights': {c['name']: c['weight'] for c in self.data.criteria},
            'final_scores': final_scores,
            'ranking': sorted_scores
        }
        return self.results

    def _calculate_expert_weights(self) -> Dict[str, float]:
        #Равномерное распределение весов между экспертами
        num_experts = len(self.data.experts)
        return {expert: 1.0 / num_experts for expert in self.data.experts}

    def _normalize_ratings(self) -> Dict[str, Dict[str, Dict[str, float]]]:
        #Нормализация оценок для каждого эксперта
        normalized = {}
        for rating in self.data.ratings:
            alt = rating['alternative']
            crit = rating['criteria']
            expert = rating['expert']
            value = rating['value']

            max_val = next(c['scale'][-1] for c in self.data.criteria if c['name'] == crit)

            if alt not in normalized:
                normalized[alt] = {}
            if crit not in normalized[alt]:
                normalized[alt][crit] = {}

            normalized[alt][crit][expert] = value / max_val
        return normalized

    def _aggregate_ratings(self,
                           normalized: Dict[str, Dict[str, Dict[str, float]]],
                           expert_weights: Dict[str, float]) -> Dict[str, Dict[str, float]]:
        #Агрегация оценок экспертов с учетом их весов
        aggregated = {}
        for alt, crit_data in normalized.items():
            aggregated[alt] = {}
            for crit, expert_values in crit_data.items():
                # Средневзвешенное по экспертам
                aggregated_score = sum(
                    value * expert_weights[expert]
                    for expert, value in expert_values.items()
                )
                aggregated[alt][crit] = round(aggregated_score, 4)
        return aggregated

    def _calculate_final_scores(self,
                                aggregated: Dict[str, Dict[str, float]]) -> Dict[str, float]:
        """Расчет финальных оценок с учетом весов критериев"""
        scores = {}
        crit_weights = {c['name']: c['weight'] for c in self.data.criteria}

        for alt, crit_values in aggregated.items():
            total = sum(
                value * crit_weights[crit]
                for crit, value in crit_values.items()
            )
            scores[alt] = round(total, 2)
            return scores