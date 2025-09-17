
# strategy_guard.py — Balanced & Flexible anti-reverse with strong protections
import os, time, hashlib, pandas as pd
from collections import deque

def _fenv(k, d): 
    try: return float(os.getenv(k, d))
    except: return float(d)
def _ienv(k, d):
    try: return int(os.getenv(k, d))
    except: return int(d)
def _benv(k, d):
    return os.getenv(k, str(d)).strip().lower() in ("1","true","yes","y","on")

def _sigkey(symbol, tf, side, price):
    raw = f"{symbol}|{tf}|{side}|{round(float(price or 0),6)}"
    return hashlib.sha1(raw.encode()).hexdigest()

def attach_guard(userbot):
    # ===== Balanced defaults (flexible but safe) =====
    MAX_TRADES_PER_HOUR    = _ienv("MAX_TRADES_PER_HOUR", 4)   # أكثر مرونة
    COOLDOWN_AFTER_CLOSE   = _ienv("COOLDOWN_AFTER_CLOSE", 420) # 7 دقائق
    MIN_BARS_BETWEEN_FLIPS = _ienv("MIN_BARS_BETWEEN_FLIPS", 6)
    ANTI_REENTRY_MIN_ATR   = _fenv("ANTI_REENTRY_MIN_ATR", 0.25)

    USE_FILTERS            = _benv("USE_DIRECTION_FILTERS", True)
    MIN_ADX                = _fenv("MIN_ADX", 20.0)  # أخف من 22
    RSI_BUY_MIN            = _fenv("RSI_BUY_MIN", 51.0)
    RSI_SELL_MAX           = _fenv("RSI_SELL_MAX", 49.0)
    SPIKE_ATR_MULT         = _fenv("SPIKE_ATR_MULT", 1.9)
    MIN_TP_PERCENT         = _fenv("MIN_TP_PERCENT", 0.70)

    ATR_PCT_MIN            = _fenv("ATR_PCT_MIN", 0.005)  # 0.50%
    ATR_PCT_MAX            = _fenv("ATR_PCT_MAX", 0.060)  # 6%

    EXPLOSION_ATR_MOVE     = _fenv("EXPLOSION_ATR_MOVE", 2.2)
    EXPLOSION_RANGE_MOVE   = _fenv("EXPLOSION_RANGE_MOVE", 2.5)
    EXPLOSION_ATR_PCT_BOOST= _fenv("EXPLOSION_ATR_PCT_BOOST", 1.5)
    COOLDOWN_EXPLOSION_BARS= _ienv("COOLDOWN_EXPLOSION_BARS", 8)  # أخف من 10

    ENFORCE_TRADE_PORTION  = _benv("ENFORCE_TRADE_PORTION", True)
    TARGET_TRADE_PORTION   = _fenv("TARGET_TRADE_PORTION", 0.60)

    # state
    recent_ts = deque()
    seen_keys = deque(maxlen=256)
    state = {"last_close_ts": 0.0, "last_flip_bar": -10, "explosion_cooldown": 0}

    # enforce trade portion 60%
    if ENFORCE_TRADE_PORTION:
        try:
            setattr(userbot, "TRADE_PORTION", TARGET_TRADE_PORTION)
            print(f"[guard] TRADE_PORTION enforced -> {TARGET_TRADE_PORTION:.2f}")
        except Exception:
            pass

    def _trim_hour():
        now = time.time()
        while recent_ts and now - recent_ts[0] > 3600:
            recent_ts.popleft()

    def _metrics():
        price  = float(getattr(userbot, "current_price", 0.0) or 0.0)
        atr    = float(getattr(userbot, "current_atr", 0.0) or 0.0)
        adx    = float(getattr(userbot, "adx_value", 0.0) or 0.0)
        rsi    = float(getattr(userbot, "rsi_value", 0.0) or 0.0)
        ema200 = float(getattr(userbot, "ema_200_value", 0.0) or 0.0)
        sym    = getattr(userbot, "SYMBOL", "DOGE-USDT")
        tf     = getattr(userbot, "INTERVAL", "15m")
        pos    = bool(getattr(userbot, "position_open", False))
        qty    = float(getattr(userbot, "current_quantity", 0.0) or 0.0)
        return price, atr, adx, rsi, ema200, sym, tf, pos, qty

    def _no_trade(msg, extra=""):
        base = f"🚫 NO-TRADE: {msg}"
        if extra:
            base += f" | {extra}"
        print(base)

    def _spike(curr, prev, atr):
        try: return abs(curr - prev) > SPIKE_ATR_MULT * max(atr, 1e-9)
        except: return False

    def _tp_pct(price, side, atr):
        try:
            tp, _sl = userbot.calculate_tp_sl(price, atr if atr>0 else 1e-6, side)
        except Exception:
            tp = price + 1.2*atr if side=="BUY" else price - 1.2*atr
        try: return abs(tp - price) / max(price, 1e-9) * 100.0
        except: return 0.0

    # Wrap close_position for cumulative PnL visibility
    _orig_close = userbot.close_position
    def _wrap_close(reason, exit_price):
        ok = _orig_close(reason, exit_price)
        state["last_close_ts"] = time.time()
        try:
            cp = float(getattr(userbot, "compound_profit", 0.0) or 0.0)
            t  = int(getattr(userbot, "total_trades", 0) or 0)
            w  = int(getattr(userbot, "successful_trades", 0) or 0)
            l  = int(getattr(userbot, "failed_trades", 0) or 0)
            print(f"💼 CLOSE [{reason}] cumulative={cp:.4f} USDT | trades {t} (W:{w}/L:{l})")
        except Exception as e:
            print(f"[guard] close log warn: {e}")
        return ok
    userbot.close_position = _wrap_close

    # Wrap place_order with protections + verbose indicator snapshot
    _orig_place = userbot.place_order
    def _wrap_place(side, qty):
        price, atr, adx, rsi, ema200, sym, tf, pos_open, cur_qty = _metrics()

        # snapshot indicators for logs
        print(f"[indicators] price={price:.6f} atr={atr:.6f} adx={adx:.2f} rsi={rsi:.2f} ema200={ema200:.6f} side={side}")

        since_close = time.time() - state["last_close_ts"]
        if since_close < COOLDOWN_AFTER_CLOSE:
            _no_trade("cooldown", f"remain={int(COOLDOWN_AFTER_CLOSE - since_close)}s")
            return False

        _trim_hour()
        if len(recent_ts) >= MAX_TRADES_PER_HOUR:
            _no_trade("max trades/hour reached")
            return False

        skey = _sigkey(sym, tf, side, price)
        if skey in seen_keys:
            _no_trade("duplicate signal")
            return False

        if price <= 0:
            _no_trade("invalid price")
            return False
        atr_pct = atr / price if price else 0.0
        if atr_pct < ATR_PCT_MIN or atr_pct > ATR_PCT_MAX:
            _no_trade("atr% window", f"{atr_pct:.4%} not in [{ATR_PCT_MIN:.2%},{ATR_PCT_MAX:.2%}]")
            return False

        # trend filters
        if USE_FILTERS:
            try:
                df = userbot.get_klines()
                cc = float(df['close'].iloc[-1]); pc = float(df['close'].iloc[-2])
                hi = float(df['high'].iloc[-1]); lo = float(df['low'].iloc[-1])
            except Exception:
                df = None; cc = price; pc = price; hi = price; lo = price

            if _spike(cc, pc, atr):
                _no_trade("spike candle")
                return False

            if adx < MIN_ADX:
                _no_trade("weak trend", f"ADX {adx:.1f} < {MIN_ADX}")
                return False

            if side == "BUY":
                if ema200 and not (price > ema200): 
                    _no_trade("BUY vs EMA200")
                    return False
                if rsi < RSI_BUY_MIN:
                    _no_trade("BUY RSI", f"{rsi:.1f} < {RSI_BUY_MIN}")
                    return False
            else:
                if ema200 and not (price < ema200): 
                    _no_trade("SELL vs EMA200")
                    return False
                if rsi > RSI_SELL_MAX:
                    _no_trade("SELL RSI", f"{rsi:.1f} > {RSI_SELL_MAX}")
                    return False

            if _tp_pct(price, side, atr) < MIN_TP_PERCENT:
                _no_trade("R:R too small")
                return False

            # explosion
            move_abs = abs(cc - pc)
            range_move = hi - lo
            current_atr_pct = atr / max(price,1e-9)
            try:
                last20 = pd.Series([abs(float(df['high'].iloc[i]-df['low'].iloc[i])) for i in range(max(0,len(df)-20), len(df))]).mean()
                avg_atr_pct = float(last20 / max(price,1e-9)) if last20 else current_atr_pct
            except Exception:
                avg_atr_pct = current_atr_pct
            explosion = (move_abs >= EXPLOSION_ATR_MOVE*atr) or (range_move >= EXPLOSION_RANGE_MOVE*atr) or (current_atr_pct >= EXPLOSION_ATR_PCT_BOOST*avg_atr_pct)
            if explosion:
                _no_trade("explosion filter")
                state["explosion_cooldown"] = COOLDOWN_EXPLOSION_BARS
                return False

            if state["explosion_cooldown"] > 0:
                state["explosion_cooldown"] -= 1
                _no_trade("explosion cooldown")
                return False

        # Anti-reentry near entry when position already open
        try:
            ent = float(getattr(userbot, "entry_price", 0.0) or 0.0)
            if pos_open and abs(price - ent) < ANTI_REENTRY_MIN_ATR * max(atr, 1e-9):
                _no_trade("anti-reentry (near entry within ATR)")
                return False
        except Exception:
            pass

        # Quantity sanity vs 60% capital (with leverage 10x)
        try:
            from bingx_balance import get_balance_usdt
            bal = float(get_balance_usdt())
            lev = float(getattr(userbot, "LEVERAGE", 10))
            portion = TARGET_TRADE_PORTION if ENFORCE_TRADE_PORTION else float(getattr(userbot,"TRADE_PORTION", TARGET_TRADE_PORTION))
            max_qty = round(((bal + float(getattr(userbot,"compound_profit",0.0))) * portion * lev) / max(price,1e-9), 2)
            if qty > max_qty * 1.05:
                _no_trade("qty > allowed", f"qty={qty}, max={max_qty}")
                return False
        except Exception as e:
            print(f"[guard] qty check warn: {e}")

        # Execute
        ok = _orig_place(side, qty)
        if ok:
            try:
                ep = float(getattr(userbot, "entry_price", 0.0) or 0.0)
                tp = float(getattr(userbot, "tp_price", 0.0) or 0.0)
                sl = float(getattr(userbot, "sl_price", 0.0) or 0.0)
                print(f"✅ TRADE OPENED | {side} qty={qty} entry={ep:.6f} tp={tp:.6f} sl={sl:.6f} | price={price:.6f} atr={atr:.6f} adx={adx:.2f} rsi={rsi:.2f}")
            except Exception:
                print(f"✅ TRADE OPENED | {side} qty={qty}")
            recent_ts.append(time.time())
            seen_keys.append(_sigkey(sym, tf, side, price))
        else:
            _no_trade("exchange rejected/core guard")
        return ok

    userbot.place_order = _wrap_place
    print("✅ strategy_guard attached (balanced & flexible).")
