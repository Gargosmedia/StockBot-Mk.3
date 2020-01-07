from bs4 import BeautifulSoup
import requests
import time
from datetime import date, timedelta
import telegram
import apireds 

ellie = telegram.Bot(token=apireds.TELEGA_TOKEN)

screenerUrl = 'https://finviz.com/screener.ashx?v=111&f=an_recom_buybetter,sec_technology,sh_curvol_o500,sh_price_o15,ta_rsi_os40&ft=4&o=-volume'
cnnURL = 'https://money.cnn.com/quote/forecast/forecast.html?symb='
tickerUrl = 'https://finviz.com/quote.ashx?t='
userAgent = 'Mozilla/5.0 (Windows NT 6.1; Win64; x64)'

portfolioDict = {'$':1000}
concStocks = 3 
singleStockMinBudget = 100
upperThreshold = 0.2
lowerThreshold = 0.1
cnnCoeficient=0.8  


def ParseCNN(tickers): 
    headers = { 'User-Agent' : userAgent } 
    forecastDict = {}
    orderedForecastList = []

    for ticker in tickers:
        response = requests.get(cnnURL+ticker, headers=headers) 
        forecast = response.text.split('The median estimate represents a <span class="posData">')[1].split('</span>')[0]

        if forecast.startswith('+'):
            forecast=forecast[1:-1]
            forecastDict[ticker]=float(forecast)
        else:
            print("Ticker ", ticker, ' has negative  forecast : ', forecast)

    orderingList = sorted(forecastDict, key=forecastDict.get, reverse=True)

    for i in orderingList:
        orderedForecastList.append([i, forecastDict[i]])   # [ticker, forecasted value]

    return(orderedForecastList)


def ParseScreener(url, use):
    dict={}
    headers = { 'User-Agent' : userAgent }
    response = requests.get(url, headers=headers)
    page = response.text
    soup = BeautifulSoup(page, 'html.parser')
    
    if (use == 1):
        for line in soup.findAll('tr',attrs={"class":"table-dark-row-cp"}):

            lineAttrs = line.findAll('a', attrs={"class":"screener-link"})
            attrsList=[]

            for value in line.findAll('a', attrs={"class":"screener-link"}):
                attrsList.append(value.getText())

            name = line.find('a', attrs={"class":"screener-link-primary"}).getText()
            fullName = attrsList.pop(1)
            dict[name]=attrsList

        return dict

    elif (use == 2):
        lines = soup.findAll('tr',attrs={"class":"table-dark-row"})
        fields = lines[10].findAll('b')
        price=fields[5].getText()

        return price


def ReadPortfolio():
    global portfolioDict

    try:
        with open('portfolio.txt', 'r') as portfolio:
            portfolieVar=portfolio.read()
            portfolioDict = eval(portfolieVar)
    except:
        portfolioDict = {'$':1000}
        with open('portfolio.txt', 'w') as portfolio:
            portfolio.write(str(portfolioDict))

    return portfolioDict


def WritePortfolio():
    global portfolioDict
    with open('portfolio.txt', 'w') as portfolio:
        portfolio.write(str(portfolioDict))

    print('Wrote:\n',portfolioDict, '\n--------------------------------------------------')
    BuildSendMessage()
    return portfolioDict


def BuildSendMessage():
    message=''
    currentAssetEstimation = portfolioDict['$']

    for key, value in portfolioDict.items():
        message += str(key) + ': ' + str(value) + '\n\n'
        if(type(value) != float):
            currentAssetEstimation += round(value['price'] * value['amount'], 2)

    message += ('========\nCAE : ' + str(round(currentAssetEstimation,2)) + '$')

    SendMessage(message=message)


def Buy(ticker,forecast, budget):
    global portfolioDict
    #Can only buy one time of one ticker - check before request. Can set to average the prices for multiple buy requests but no need
    
    if (ticker in portfolioDict and portfolioDict[ticker]['amount'] != 0):
        return portfolioDict

    money = portfolioDict['$']
    price = float(ParseScreener(tickerUrl+ticker,2))
    amount = int(budget/price)
    print(price, ' amount: ', amount)
    #Substracting total money
    portfolioDict['$'] = round(money-(price*amount),2)
    portfolioDict[ticker]={'price': price,'amount': amount, 'predictedPercentageIncrease': round(forecast/100,2), 'dateBought': date.today(), 'dateLimitSell': (date.today() + timedelta(days=3)) }

    return WritePortfolio()


def Sell(ticker):
    global portfolioDict

    #Only selling all of the tickers
    money = portfolioDict['$']
    amount = portfolioDict[ticker]['amount']
    price =  float(ParseScreener((tickerUrl + ticker),2))
    portfolioDict['$'] = round(money+(price*amount),2)
    #Deleting from dict
    portfolioDict[ticker]['amount']=0
    
    return WritePortfolio()
    

def SendOrders(potentialBuyOrdered):
    global concStocks

    while (portfolioDict['$']/concStocks < singleStockMinBudget):
        print('Not enough money for ', concStocks, '. Downscaling to ', concStocks-1 )
        concStocks -= 1

        if (concStocks ==  0):
            return False

    budget = portfolioDict['$']/concStocks  # Can split them to len(potentialButOrdered) when its less then concStocks but to limit risk will budget to 3 even if theres only 2 to buy

    if (len(potentialBuyOrdered) >= concStocks):
        for ticker, forecast in potentialBuyOrdered[:concStocks]:
            Buy(ticker, forecast, budget)
    else:
        for ticker, forecast in potentialBuyOrdered:
            Buy(ticker, forecast, budget)

    # TODO: Look for better implementation of the check ^

    return True


def CheckSellPortfolio():
    global portfolioDict

    for ticker, attributes in portfolioDict.items():
       
        if ticker != '$':
            predictedIncrease = attributes['predictedPercentageIncrease']
            priceMarket =  float(ParseScreener((tickerUrl + ticker),2))
            pricePortfolio = attributes['price']
            dateBought = attributes['dateBought']
            dateLimitSell = attributes['dateLimitSell']

            if predictedIncrease > upperThreshold:
                predictedIncrease = upperThreshold
            else:
                predictedIncrease = predictedIncrease*cnnCoeficient

            limitSellPrice = pricePortfolio*(1+predictedIncrease)

            if (priceMarket >= limitSellPrice):
                Sell(ticker)
            elif (priceMarket < pricePortfolio*(1-lowerThreshold)):
                Sell(ticker)
            elif (dateBought >= dateLimitSell):
                Sell(ticker)

            # ^ Leaving ifs separate to modify later 

    return portfolioDict


def SendMessage(chatid = '561191777', message = 'Test Message'):
    ellie.sendMessage(chatid, message)


def Main():
    ReadPortfolio()

    while True:
        try: 
            CheckSellPortfolio()
            potentialBuy = ParseScreener(screenerUrl, 1)
            potentialBuyOrdered = ParseCNN(potentialBuy.keys())
            SendOrders(potentialBuyOrdered)
            # SendOrders(ParseCNN(ParseScreener(screenerUrl, 1).keys()))  # in one line
            time.sleep(10)
            
        except Exception as e:
            print("Error: ",  e)
            pass

Main()