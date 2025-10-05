import streamlit as st
import requests
from abc import ABC, abstractmethod
from datetime import datetime, date, timedelta
from pytz import timezone

# 1. Config クラス (設定外部化)
class Config:
    TIMEZONE = 'Asia/Tokyo'
    FORECAST_LOCATION_ID = '44132'
    HISTORICAL_LOCATION_ID = '47662'
    RAIN_THRESHOLD_MM = 0.0
    SESSION_KEY_BETS = 'weekly_bets'
    MOCK_SOURCE_TEXT = "予報は現在モックです。実際の予報データAPIと切り替え可能です。"

# 2. アダプター層 (アダプターパターン適用)
# 2.1 抽象クラス (インターフェース)
class ForecastAdapter(ABC):
    @abstractmethod
    def fetch_forecast_data(self, location_id: str) -> dict:
        pass

class HistoricalAdapter(ABC):
    @abstractmethod
    def fetch_historical_rainfall(self, location_id: str) -> dict:
        pass

# 2.2 具象クラス (実装)
class CultivationForecastAPI(ForecastAdapter):
    def fetch_forecast_data(self, location_id: str) -> dict:
        return {'status': 'mock_data', 'message': '予報API未実装'}

class CultivationHistoricalAPI(HistoricalAdapter):
    BASE_URL = "https://api.cultivationdata.net/past"

    def fetch_historical_rainfall(self, location_id: str) -> dict:
        params = {'no': location_id}
        try:
            response = requests.get(self.BASE_URL, params=params, timeout=5)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            st.error(f"APIへの接続に失敗しました: {e}")
            return {'error': str(e), 'data_status': 'failed'}

# 3. WeatherForecaster クラス (データ変換・判定ロジック)
class WeatherForecaster:
    def __init__(self, forecast_adapter: ForecastAdapter, historical_adapter: HistoricalAdapter, location_id: str):
        self._f_adapter = forecast_adapter
        self._h_adapter = historical_adapter
        self._location_id = location_id

    def _transform_historical_data(self, raw_data: dict, target_day: date) -> dict:
        # This is a placeholder transformation.
        # The actual key for precipitation needs to be identified from the real API response.
        # For PoC, we assume the API returns a simple structure.
        # Example for a hypothetical structure:
        # precipitation_mm = raw_data.get('daily_data', {}).get(target_day.strftime('%Y-%m-%d'), {}).get('rainfall_mm', 0.0)

        # Based on the provided API URL, the actual data structure is likely different.
        # Let's assume a key 'precipitation' exists for the target date for now.
        precipitation_mm = raw_data.get('precipitation', 0.0) # Placeholder

        return {
            'date': target_day.strftime('%Y-%m-%d'),
            'precipitation_mm': precipitation_mm,
            'is_rain_result': precipitation_mm > Config.RAIN_THRESHOLD_MM
        }

    def get_weekly_forecast(self) -> list[dict]:
        self._f_adapter.fetch_forecast_data(Config.FORECAST_LOCATION_ID)

        forecasts = []
        jst_now = datetime.now(timezone(Config.TIMEZONE))
        for i in range(1, 8):
            forecast_date = (jst_now + timedelta(days=i)).strftime('%Y-%m-%d')
            is_rain = (i % 2 == 0)

            forecasts.append({
                'date': forecast_date,
                'precipitation_mm': 10.0 if is_rain else 0.0,
                'is_rain_forecast': is_rain,
                'source': Config.MOCK_SOURCE_TEXT
            })
        return forecasts

    def get_historical_result(self, date_str: str) -> dict:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        jst_now = datetime.now(timezone(Config.TIMEZONE))

        # This check is conceptual. The /past API fetches "yesterday's" data.
        # A more robust implementation might be needed depending on when this runs.
        yesterday = (jst_now - timedelta(days=1)).date()
        if target_date != yesterday:
            # For this PoC, we will still attempt to fetch but acknowledge the logic gap.
            # In a real app, you might return an error or adjust the call.
            pass

        raw_data = self._h_adapter.fetch_historical_rainfall(Config.HISTORICAL_LOCATION_ID)

        if raw_data.get('data_status') == 'failed' or 'error' in raw_data:
            return {'error': 'データ取得失敗'}

        # The API documentation is needed to correctly parse this.
        # Let's assume the API returns data for the previous day and we can extract it.
        # For the PoC, we will simulate this transformation.
        # A sample successful response might look like:
        # { "id": "47662", "datetime": "2023-10-26T00:00:00+09:00", "precipitation": 5.5, ... }

        # Let's simulate finding the correct data for the target date.
        # In a real scenario, we'd parse the 'raw_data' list/dict.
        # For this PoC, we'll just pass the raw data to the transformer.
        # The key 'rain_amount_extracted' from the spec is implemented as 'precipitation' here.

        transformed_data = self._transform_historical_data(raw_data, target_date)
        return transformed_data

# 4. BettingManager クラス (投票・オッズ管理)
class BettingManager:
    def __init__(self):
        if Config.SESSION_KEY_BETS not in st.session_state:
            st.session_state[Config.SESSION_KEY_BETS] = {}

    def record_bet(self, date_str: str, bet_type: str):
        if date_str not in st.session_state[Config.SESSION_KEY_BETS]:
            st.session_state[Config.SESSION_KEY_BETS][date_str] = {'rain': 0, 'no_rain': 0}

        if bet_type == 'rain':
            st.session_state[Config.SESSION_KEY_BETS][date_str]['rain'] += 1
        elif bet_type == 'no_rain':
            st.session_state[Config.SESSION_KEY_BETS][date_str]['no_rain'] += 1

    def get_odds(self, date_str: str) -> dict:
        bets = st.session_state[Config.SESSION_KEY_BETS].get(date_str, {'rain': 0, 'no_rain': 0})
        rain_count = bets['rain']
        no_rain_count = bets['no_rain']
        total = rain_count + no_rain_count

        if total == 0:
            return {'total': 0, 'rain_odds': 0, 'no_rain_odds': 0, 'rain_count': 0, 'no_rain_count': 0}

        rain_odds = total / rain_count if rain_count > 0 else total + 1
        no_rain_odds = total / no_rain_count if no_rain_count > 0 else total + 1

        return {
            'total': total,
            'rain_odds': round(rain_odds, 2),
            'no_rain_odds': round(no_rain_odds, 2),
            'rain_count': rain_count,
            'no_rain_count': no_rain_count
        }

# 5. メインの Streamlit UI (main 関数)
def main():
    # 依存オブジェクトを初期化
    f_adapter = CultivationForecastAPI()
    h_adapter = CultivationHistoricalAPI()
    forecaster = WeatherForecaster(f_adapter, h_adapter, Config.FORECAST_LOCATION_ID)
    manager = BettingManager()

    st.title("🌧️ 1週間分の雨予報チャレンジ (PoC)")
    st.markdown("明日の東京は雨が降る？降らない？ 1週間先までのみんなの予想を見てみよう！")

    # --- 結果発表セクション (モック表示) ---
    st.subheader("🎉 昨日の結果発表 (モック)")
    jst_now = datetime.now(timezone(Config.TIMEZONE))
    yesterday = jst_now.date() - timedelta(days=1)

    # モックデータで結果を固定表示
    mock_result = {
        'is_rain_result': True,
        'precipitation_mm': 15.5
    }
    result_icon = "💧 **雨が降りました**" if mock_result['is_rain_result'] else "☀️ **雨は降りませんでした**"
    st.markdown(f"**結果 ({yesterday.strftime('%Y-%m-%d')}):** {result_icon}")
    st.write(f"観測された降水量: {mock_result['precipitation_mm']} mm")
    st.caption("データソース: モックデータ (表示確認用)")
    st.markdown("---")

    # --- 予報と投票セクション ---
    st.header("🗓️ 今後の雨予報チャレンジ")
    weekly_forecasts = forecaster.get_weekly_forecast()
    today = jst_now.date()

    for day_forecast in weekly_forecasts:
        date_str = day_forecast['date']
        forecast_date = datetime.strptime(date_str, '%Y-%m-%d').date()

        st.subheader(f"{date_str} の予報と投票")

        # 予報の表示
        forecast_icon = "💧 雨" if day_forecast['is_rain_forecast'] else "☀️ 晴れ"
        st.markdown(f"**モック予報:** {forecast_icon}")
        st.caption(f"出典: {day_forecast['source']}")

        # 投票セクション
        if forecast_date > today:
            col1, col2 = st.columns(2)
            with col1:
                if st.button(f"雨が降ると思う", key=f"rain_{date_str}"):
                    manager.record_bet(date_str, 'rain')
                    st.rerun()

            with col2:
                if st.button(f"降らないと思う", key=f"no_rain_{date_str}"):
                    manager.record_bet(date_str, 'no_rain')
                    st.rerun()

        # オッズの表示
        odds = manager.get_odds(date_str)
        st.write(f"現在の投票数: {odds['total']} 票")
        if odds['total'] > 0:
            st.write(f"「雨」のオッズ: {odds['rain_odds']} (投票数: {odds['rain_count']})")
            st.write(f"「降らない」のオッズ: {odds['no_rain_odds']} (投票数: {odds['no_rain_count']})")
        else:
            st.write("まだ投票がありません。")

        st.markdown("---")

    # 法的要件
    st.caption(
        "【気象データ利用に関する注意】"
        "当アプリの予報は、現在モックデータで動作しています。結果発表は、気象庁の公開データ (cultivationdata.net 経由) を元に判定します。 "
        "アプリ開発者は独自の予報を行っておらず、データの利用については、気象庁の利用規約を遵守しています。"
    )

if __name__ == "__main__":
    main()