#!/usr/bin/env python3
"""
Debug script to test AlphaTrader model loading and inference.
"""

import os
import sys
import numpy as np

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def main():
    print("=" * 60)
    print("AlphaTrader Debug Script")
    print("=" * 60)

    # 1. Check PyTorch
    try:
        import torch
        print(f"✅ PyTorch version: {torch.__version__}")
    except ImportError:
        print("❌ PyTorch not available")
        return

    # 2. Check config
    from alpha.config import get_config
    config = get_config()
    print(f"✅ Config loaded")
    print(f"   - state_dim: {config.network.state_dim}")
    print(f"   - policy_hidden_layers: {config.network.policy_hidden_layers}")
    print(f"   - checkpoint_dir: {config.training.checkpoint_dir}")

    # 3. Check checkpoint files
    checkpoint_dir = config.training.checkpoint_dir
    print(f"\n📁 Checking checkpoint directory: {checkpoint_dir}")

    if os.path.exists(checkpoint_dir):
        files = os.listdir(checkpoint_dir)
        print(f"   Files found: {files}")

        for f in ['best_model.pt', 'final_model.pt']:
            path = os.path.join(checkpoint_dir, f)
            if os.path.exists(path):
                size = os.path.getsize(path)
                print(f"   ✅ {f}: {size} bytes")
            else:
                print(f"   ❌ {f}: not found")
    else:
        print(f"   ❌ Directory does not exist!")

    # 4. Try loading checkpoint
    checkpoint_path = os.path.join(checkpoint_dir, "final_model.pt")
    if not os.path.exists(checkpoint_path):
        checkpoint_path = os.path.join(checkpoint_dir, "best_model.pt")

    if os.path.exists(checkpoint_path):
        print(f"\n🔄 Loading checkpoint: {checkpoint_path}")
        try:
            checkpoint = torch.load(checkpoint_path, map_location='cpu', weights_only=False)
            print(f"   Keys: {list(checkpoint.keys())}")

            # Check policy state dict
            policy_sd = checkpoint.get('policy_state_dict', {})
            print(f"\n   Policy state dict layers:")
            for key, value in policy_sd.items():
                if isinstance(value, torch.Tensor):
                    print(f"      {key}: {value.shape}")

        except Exception as e:
            print(f"   ❌ Error loading: {e}")
            return
    else:
        print(f"\n❌ No checkpoint found at {checkpoint_path}")
        return

    # 5. Create policy network and load weights
    print(f"\n🧠 Creating policy network...")
    from alpha.policy_network import create_policy_network
    policy = create_policy_network(config.network)
    print(f"   Created: {type(policy).__name__}")

    # Check first layer input dimension
    if hasattr(policy, 'hidden'):
        first_layer = None
        for module in policy.hidden.modules():
            if isinstance(module, torch.nn.Linear):
                first_layer = module
                break
        if first_layer:
            print(f"   First layer input dim: {first_layer.in_features}")
            print(f"   First layer output dim: {first_layer.out_features}")

    # Load weights
    print(f"\n🔄 Loading weights into policy...")
    try:
        policy.load_state_dict(checkpoint['policy_state_dict'])
        print(f"   ✅ Weights loaded successfully!")
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return

    # 6. Test with dummy state
    print(f"\n🧪 Testing with dummy state...")
    from alpha.market_state import MarketState, IndicatorState, SentimentState, ScoreState

    state = MarketState()
    state.indicators["BTC"] = IndicatorState(
        symbol="BTC",
        price=95000,
        ema20=94500,
        ema50=94000,
        rsi_14=55,
        macd=0.15,
        adx=28,
    )
    state.sentiment = SentimentState(fear_greed_index=60)
    state.scores["BTC"] = ScoreState(
        score_bullish=20,
        score_bearish=10,
        net_score=10,
        direction="LONG",
        confidence="NORMAL",
    )
    state.balance_usd = 1000
    state.equity_usd = 1000

    # Get state vector
    state_vec = state.to_vector("BTC")
    print(f"   State vector shape: {state_vec.shape}")
    print(f"   State vector range: [{state_vec.min():.3f}, {state_vec.max():.3f}]")
    print(f"   Non-zero elements: {np.count_nonzero(state_vec)}")

    # Test inference
    print(f"\n🎯 Running inference...")
    try:
        action, policy_output = policy.get_action(state, "BTC")
        print(f"   Action: {action.action_type.name}")
        print(f"   Confidence: {action.confidence:.4f} ({action.confidence*100:.1f}%)")
        print(f"   Leverage: {action.leverage}")
        print(f"   Position Size: {action.position_size_pct:.2f}x")
        print(f"\n   Action probabilities:")
        for i, prob in enumerate(policy_output.action_probs):
            action_name = ['HOLD', 'OPEN_LONG', 'OPEN_SHORT', 'CLOSE'][i]
            print(f"      {action_name}: {prob:.4f} ({prob*100:.1f}%)")
        print(f"\n   Entropy: {policy_output.entropy:.4f}")

    except Exception as e:
        import traceback
        print(f"   ❌ Error: {e}")
        traceback.print_exc()

    # 7. Test with real indicators (if available)
    print(f"\n📊 Testing with real indicators...")
    try:
        from alpha.indicators_standalone import get_hyperliquid_indicators, get_fear_greed_index

        ind_text, ind_json = get_hyperliquid_indicators("BTC")
        print(f"   BTC indicators loaded:")
        print(f"      Price: ${ind_json.get('price', 0):,.2f}")
        print(f"      RSI: {ind_json.get('rsi_14', 0):.1f}")
        print(f"      MACD: {ind_json.get('macd', 0):.4f}")
        print(f"      ADX: {ind_json.get('adx', 0):.1f}")

        fg = get_fear_greed_index()
        print(f"   Fear & Greed: {fg.get('value', 50)} ({fg.get('classification', 'N/A')})")

        # Create state from real data
        from alpha.market_state import create_state_from_data
        real_state = create_state_from_data(
            indicators_data={"BTC": ind_json},
            sentiment_data=fg,
            forecast_data={},
            score_data={},
            position_data=None,
            account_data={"balance_usd": 1000, "equity_usd": 1000},
        )

        # Get action
        action, policy_output = policy.get_action(real_state, "BTC")
        print(f"\n   🎯 Real data decision:")
        print(f"      Action: {action.action_type.name}")
        print(f"      Confidence: {action.confidence:.4f} ({action.confidence*100:.1f}%)")
        print(f"      Action probs: {[f'{p:.2f}' for p in policy_output.action_probs]}")

    except Exception as e:
        import traceback
        print(f"   ⚠️ Could not test with real indicators: {e}")
        traceback.print_exc()

    print("\n" + "=" * 60)
    print("Debug complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
