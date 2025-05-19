from typing import Dict, Any
from pathlib import Path
import pandas as pd


class ExcelExporter:
    def __init__(self, results: Dict[str, Any]):
        self.results = results

    def export(self, output_path: Path):
        print(f"[DEBUG] Начало экспорта в {output_path}")
        try:
            # Проверка обязательных ключей
            required_keys = ['criteria_weights', 'expert_weights', 'ranking']
            for key in required_keys:
                if key not in self.results:
                    raise KeyError(f"Отсутствует ключ: {key}")

            with pd.ExcelWriter(output_path) as writer:
                # Лист 1: Веса критериев
                pd.DataFrame.from_dict(
                    self.results['criteria_weights'],
                    orient='index',
                    columns=['Weight']
                ).to_excel(writer, sheet_name='Criteria Weights')

                # Лист 2: Веса экспертов
                pd.DataFrame.from_dict(
                    self.results['expert_weights'],
                    orient='index',
                    columns=['Weight']
                ).to_excel(writer, sheet_name='Expert Weights')

                # Лист 3: Рейтинг альтернатив
                ranking_data = [
                    {
                        "Rank": idx + 1,
                        "Alternative": alt,
                        "Final Score": score
                    }
                    for idx, (alt, score) in enumerate(self.results['ranking'])
                ]

                pd.DataFrame(ranking_data).to_excel(
                    writer,
                    sheet_name='Alternatives Ranking',
                    index=False,
                    columns=['Rank', 'Alternative', 'Final Score'],
                    float_format="%.3f"  # Формат чисел с тремя знаками после запятой
                )

        except Exception as e:
            print(f"[ERROR] Ошибка экспорта: {str(e)}")
            raise