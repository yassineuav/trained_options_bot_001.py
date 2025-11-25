import numpy as np
from scipy.stats import norm
import math

class OptionsPricing:
    def __init__(self, risk_free_rate=0.045):
        self.r = risk_free_rate

    def black_scholes(self, S, K, T, sigma, option_type='call'):
        """
        Calculate Black-Scholes option price.
        S: Underlying Price
        K: Strike Price
        T: Time to Expiration (in years)
        sigma: Implied Volatility (annualized)
        option_type: 'call' or 'put'
        """
        if T <= 0:
            return max(0, S - K) if option_type == 'call' else max(0, K - S)
            
        d1 = (np.log(S / K) + (self.r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
        d2 = d1 - sigma * np.sqrt(T)
        
        if option_type == 'call':
            price = S * norm.cdf(d1) - K * np.exp(-self.r * T) * norm.cdf(d2)
        else:
            price = K * np.exp(-self.r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)
            
        return price

    def calculate_greeks(self, S, K, T, sigma, option_type='call'):
        """
        Calculate Greeks for an option.
        """
        if T <= 0:
            return {'delta': 0, 'gamma': 0, 'theta': 0, 'vega': 0}

        d1 = (np.log(S / K) + (self.r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
        d2 = d1 - sigma * np.sqrt(T)
        
        N_prime_d1 = norm.pdf(d1)
        
        if option_type == 'call':
            delta = norm.cdf(d1)
            theta = (- (S * sigma * N_prime_d1) / (2 * np.sqrt(T)) 
                     - self.r * K * np.exp(-self.r * T) * norm.cdf(d2))
        else:
            delta = norm.cdf(d1) - 1
            theta = (- (S * sigma * N_prime_d1) / (2 * np.sqrt(T)) 
                     + self.r * K * np.exp(-self.r * T) * norm.cdf(-d2))

        gamma = N_prime_d1 / (S * sigma * np.sqrt(T))
        vega = S * np.sqrt(T) * N_prime_d1 / 100 # Vega is usually per 1% change in vol
        
        return {
            'delta': delta,
            'gamma': gamma,
            'theta': theta / 365, # Daily theta
            'vega': vega
        }

    def get_atm_strike(self, price):
        """Returns the nearest integer strike price."""
        return round(price)

    def estimate_volatility(self, history_prices, window=20):
        """
        Estimate annualized volatility from recent price history.
        """
        log_returns = np.log(history_prices / history_prices.shift(1))
        # 15m bars -> ~26 bars/day * 252 days = 6552 bars/year
        # Or simply: std_dev * sqrt(number of periods in a year)
        # 15m in trading day (6.5 hours) = 26 periods.
        # 252 trading days.
        # Total periods = 26 * 252 = 6552
        vol = log_returns.rolling(window=window).std() * np.sqrt(6552)
        return vol.iloc[-1] if not np.isnan(vol.iloc[-1]) else 0.20 # Default to 20% if nan
