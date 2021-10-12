from binance.helpers import round_step_size
from binance.client import Client
 
from binance import AsyncClient, BinanceSocketManager

from sklearn.linear_model import LinearRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error

import pandas as pd
import time, joblib, datetime, sys,asyncio

import telegram_send

###################
build_dict = dict()
###################
offset = 0.0005
###################
baseline = 39
###################

class Models():
    def __init__(self, symbol, timeframes):
        self.api_key = "6anuXweZQ8f9O7KpJlq5sB2zzOBueoY0EP7BQDALN5BIxq4OkXCMorJFyBqx41DM"
        self.api_secret = "ziOAlWdAZItThEt4r4dQJriqdonOY2gixZ6tCLcUZ3St9aKhcwhXgrBgyUHQeXw1"

        self.client = Client(self.api_secret, self.api_key)
        
        self.symbol = symbol

        self.timeframes = timeframes
        self.datasets = list()
        
        self.build()
        
    def historical_data(self, period, start):
        data = self.client.get_historical_klines(self.symbol, period, start)
        dataset = pd.DataFrame(data, columns=["var a", "open", "high", "low", "close", "volume", "var b", "var c",  "var d",  "var e",  "var f", "var g"])

        dataset = dataset.drop(columns=["var a", "var b", "var c",  "var d",  "var e",  "var f", "var g"])

        return dataset                                         

    def model(self, period, starting_point):
        dataset = self.historical_data(period, starting_point)
        ######################################################
        self.datasets.append(dataset)
        ######################################################
        for target in ["low", "close"]:
            X = dataset.drop(columns=target).to_numpy('float') 
            Y = dataset[target].to_numpy('float')

            X_train, X_test, Y_train, Y_test = train_test_split(X, Y, random_state=0) 
            model = LinearRegression().fit(X_train, Y_train)

            trainingset_score = model.score(X_train, Y_train)
            testset_score = model.score(X_test, Y_test)
            error_margin = mean_squared_error(model.predict(X_test), Y_test)

            prediction = model.predict(X)[-1:][0]

            telegram_send.send(messages = [f'''
                "Symbol": {self.symbol}
                "Training Score": {round(trainingset_score, 4)}
                "Test Score": {round(testset_score, 4)}
                "Margin Of Error": {round(error_margin, 8)}
                "Prediction": {round(prediction, 4)}
                "Metadata":
                    "Period": {period}
                    "Target": {target}'''])

            build_dict[self.symbol][target] = round(prediction, 4)
            build_dict[self.symbol][f"{target}_mse"] = round(error_margin, 4)
        ############################################################

    def threshold(self):
        dataset = self.historical_data(Client.KLINE_INTERVAL_1DAY, "1 Jan, 2010")
        target = "close"
        X = dataset.drop(columns=target).to_numpy('float')
        Y = dataset[target].to_numpy('float')

        X_train, X_test, Y_train, Y_test = train_test_split(X, Y, random_state=0)
        model = LinearRegression().fit(X_train, Y_train)

        trainingset_score = model.score(X_train, Y_train)
        testset_score = model.score(X_test, Y_test)
        error_margin = mean_squared_error(model.predict(X_test), Y_test)

        threshold = model.predict(X)[-1:][0]

        telegram_send.send(messages = [f'''
            Daily Threshold Analysis
                "Symbol": {self.symbol}
                "Training Score": {round(trainingset_score, 4)}
                "Test Score": {round(testset_score, 4)}
                "Margin Of Error": {round(error_margin, 8)}
                "Threshold": {round(threshold, 4)}
                "Metadata":
                    "Period": DAY
                    "Target": {target}
            '''])

        build_dict[self.symbol]["threshold"] = round(threshold, 4)

    def build(self):
        #############################################################
        self.result = list()
        #############################################################
        for timeframe in self.timeframes:
            self.result.append(self.model(timeframe[0], timeframe[1]))

        self.threshold()

        #self.results = self.model(Client.KLINE_INTERVAL_1DAY, "1 Jan, 2010")
        #self.hourly = self.model(Client.KLINE_INTERVAL_1HOUR, "1 Jan, 2020")


class Alert():
    def __init__(self, symbol, price):
        self.symbol = symbol
        self.price = price
        
        now = datetime.datetime.now()

        telegram_send.send(messages=[f"Initializing Market Monitor For The Hour {now.hour}:00"])

        loop = asyncio.get_event_loop()
        loop.run_until_complete(self.monitor())

    async def monitor(self):
        self.api_key = "6anuXweZQ8f9O7KpJlq5sB2zzOBueoY0EP7BQDALN5BIxq4OkXCMorJFyBqx41DM"
        self.api_secret = "ziOAlWdAZItThEt4r4dQJriqdonOY2gixZ6tCLcUZ3St9aKhcwhXgrBgyUHQeXw1"
        
        self.client = await AsyncClient.create(self.api_key, self.api_secret)
        
        self.socket_manager = BinanceSocketManager(self.client)
        self.socket = self.socket_manager.kline_socket(self.symbol, interval=Client.KLINE_INTERVAL_1MINUTE)

        self.token = "00:00"

        async with self.socket as sck:
            while True:
                msg = await sck.recv()
                if msg['e'] == 'error':
                    telegram_send.send(messages=[f"{msg}"])
                else:
                    data = msg['k']
                    now = datetime.datetime.now()

                    if now.minute%15 == 0 and self.token != f"{now.hour}:{now.minute}":
                        telegram_send.send(messages=[f"Market Monitor Operating For The Hour {now.hour}:00"])
                        self.token = f"{now.hour}:{now.minute}"

                    if now.minute < 58:
                        if float(data['c']) <= self.price + offset or float(data['l']) <= self.price + offset:
                            telegram_send.send(messages=[f'''
                                Price Alert: 
                                Symbol: {self.symbol}
                                Price: {float(data['c'])}
                            '''])
                            telegram_send.send(messages=[f"Exiting Market Monitor Operation For The Hour {now.hour}:00"])
                            sys.exit(0)
                    else:
                        telegram_send.send(messages=[f"Time Elasped: Exiting Market Monitor Operation For The Hour {now.hour}:00"])
                        sys.exit(0)


def main():
    telegram_send.send(messages=[f"Time: {time.ctime()}  Initializing Orion Project"])
    timeframes = [(Client.KLINE_INTERVAL_1HOUR, "1 Jan, 2010")]

    symbols = ["DOGEUSDT"]

    for coin in symbols:
        build_dict[coin] = {
                        "low": None,
                        "close": None,
                        "threshold": None,
                        "profit": None
                    }
    
    for symbol in symbols:
        Models(symbol, timeframes)

    profit = list()
    for coin in symbols:
        pips = build_dict[coin]["close"] - build_dict[coin]["low"]
        quantity = baseline/build_dict[coin]["low"]
        est_profit = quantity * pips

        build_dict[coin]["profit"] = round(est_profit, 4)
        build_dict[coin]["avg_mse"] = (build_dict[coin]["close_mse"] + build_dict[coin]["low_mse"])/2
        profit.append(round(build_dict[coin]["profit"], 8))

    coin = symbols[profit.index(max(profit))]
    result = {
        "symbol": coin,
        "close": build_dict[coin]["close"],
        "low": build_dict[coin]["low"],
        "threshold": build_dict[coin]["threshold"],
        "low_offset": offset + build_dict[coin]["low"],
        "avg. mse": round(build_dict[coin]["avg_mse"], 8),
        "profit": round(max(profit), 4)
        }

    #telegram_send.send(messages=[build_dict])
    telegram_send.send(messages=[result])

    Alert(coin, build_dict[coin]["low"])
    
if __name__ == '__main__':
    main()