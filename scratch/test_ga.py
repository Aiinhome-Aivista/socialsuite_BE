import sys
import os
import argparse

# Add app directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from app.services.connectors.google_analytics import GoogleAnalyticsConnector

def main():
    parser = argparse.ArgumentParser(description="Test Google Analytics GA4 Connector")
    parser.add_argument("--code", type=str, help="OAuth authorization code to exchange")
    parser.add_argument("--token", type=str, help="Access token to test API requests directly")
    parser.add_argument("--refresh", type=str, help="Refresh token to test token refreshing")
    parser.add_argument("--property", type=str, help="GA4 Property Resource Name (e.g., properties/123456)")
    args = parser.parse_args()

    connector = GoogleAnalyticsConnector()

    if not args.code and not args.token and not args.refresh:
        # Step 1: Print Auth URL
        state = "test_state_123"
        auth_url = connector.authorize_url(state)
        print("=" * 80)
        print("GOOGLE GA4 AUTHENTICATION TEST")
        print("=" * 80)
        print("1. Open the following URL in your browser to authorize Google Analytics access:")
        print(f"\n{auth_url}\n")
        print("2. After giving consent, copy the 'code' parameter from the redirect URL.")
        print("3. Run this script again with the code: python scratch/test_ga.py --code YOUR_CODE_HERE")
        print("=" * 80)
        return

    if args.code:
        # Step 2: Exchange Code
        print(f"Exchanging authorization code: {args.code}...")
        try:
            tokens = connector.exchange_code(args.code)
            print("\nToken Exchange Succeeded!")
            print(f"Access Token: {tokens.access_token[:30]}...")
            print(f"Refresh Token: {tokens.refresh_token}")
            print(f"Expires At: {tokens.expires_at}")
            
            # Use these tokens to list accounts
            test_apis(connector, tokens, args.property)
        except Exception as e:
            print(f"Error exchanging code: {e}")

    elif args.refresh:
        # Step 2b: Test Refresh
        from app.services.connectors.base import TokenBundle
        print(f"Refreshing token with refresh token: {args.refresh}...")
        try:
            old_bundle = TokenBundle(access_token="dummy", refresh_token=args.refresh)
            tokens = connector.refresh(old_bundle)
            print("\nToken Refresh Succeeded!")
            print(f"New Access Token: {tokens.access_token[:30]}...")
            print(f"Expires At: {tokens.expires_at}")
            
            test_apis(connector, tokens, args.property)
        except Exception as e:
            print(f"Error refreshing token: {e}")

    elif args.token:
        # Step 2c: Test API directly
        from app.services.connectors.base import TokenBundle
        tokens = TokenBundle(access_token=args.token)
        test_apis(connector, tokens, args.property)


def test_apis(connector, tokens, test_property=None):
    print("\n" + "=" * 50)
    print("TESTING ADMIN API: fetch_accounts")
    print("=" * 50)
    try:
        accounts = connector.fetch_accounts(tokens)
        print(f"Found {len(accounts)} properties:")
        for idx, acc in enumerate(accounts):
            print(f"  {idx + 1}. Name: {acc.display_name} (ID: {acc.external_id})")
        
        # Determine which property to fetch metrics for
        target_property = test_property
        if not target_property and accounts:
            target_property = accounts[0].external_id
            print(f"\nAuto-selecting first property for metrics test: {target_property}")
        
        if target_property:
            print("\n" + "=" * 50)
            print(f"TESTING DATA API: fetch_metrics for {target_property}")
            print("=" * 50)
            metrics = connector.fetch_metrics(tokens.access_token, target_property)
            print("Successfully retrieved metrics (last 30 days):")
            print(f"  Active Users (Followers column): {metrics.followers}")
            print(f"  Sessions (Likes column): {metrics.likes}")
            print(f"  Page Views (Impressions column): {metrics.impressions}")
        else:
            print("\nNo property available to test metrics.")
    except Exception as e:
        print(f"Error calling Google APIs: {e}")


if __name__ == "__main__":
    main()
