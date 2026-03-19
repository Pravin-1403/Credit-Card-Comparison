#!/usr/bin/env python3

import requests
import json
import sys
from datetime import datetime

class CreditCardAPITester:
    def __init__(self, base_url="https://smartcard-pick.preview.emergentagent.com"):
        self.base_url = base_url
        self.tests_run = 0
        self.tests_passed = 0
        self.test_results = []

    def log_result(self, test_name, success, details="", response_data=None):
        """Log test result"""
        self.tests_run += 1
        if success:
            self.tests_passed += 1
            print(f"✅ PASS: {test_name}")
        else:
            print(f"❌ FAIL: {test_name} - {details}")
        
        self.test_results.append({
            'test': test_name,
            'success': success,
            'details': details,
            'response_data': response_data
        })

    def run_test(self, name, method, endpoint, expected_status, data=None, timeout=30):
        """Run a single API test"""
        url = f"{self.base_url}/api{endpoint}"
        headers = {'Content-Type': 'application/json'}

        print(f"\n🔍 Testing: {name}")
        print(f"   URL: {url}")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, timeout=timeout)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers, timeout=timeout)
            elif method == 'PUT':
                response = requests.put(url, json=data, headers=headers, timeout=timeout)
            elif method == 'DELETE':
                response = requests.delete(url, headers=headers, timeout=timeout)

            success = response.status_code == expected_status
            response_data = None
            
            try:
                response_data = response.json() if response.content else {}
            except:
                response_data = response.text

            details = f"Status: {response.status_code}"
            if not success:
                details += f", Expected: {expected_status}, Response: {response_data}"

            self.log_result(name, success, details, response_data)
            return success, response_data

        except Exception as e:
            self.log_result(name, False, f"Exception: {str(e)}")
            return False, {}

    def test_basic_endpoints(self):
        """Test basic API endpoints"""
        print("\n" + "="*60)
        print("TESTING BASIC ENDPOINTS")
        print("="*60)
        
        # Test root endpoint
        self.run_test("API Root", "GET", "/", 200)
        
        # Test get all cards (should be empty initially)
        success, cards = self.run_test("Get All Cards (Initial)", "GET", "/cards", 200)
        if success:
            print(f"   Found {len(cards) if isinstance(cards, list) else 0} cards")

    def test_seed_cards(self):
        """Test seeding sample cards"""
        print("\n" + "="*60)
        print("TESTING SEED CARDS")
        print("="*60)
        
        success, response = self.run_test("Seed Sample Cards", "POST", "/seed-cards", 200)
        if success:
            print(f"   Response: {response}")
        
        # Verify cards were seeded
        success, cards = self.run_test("Get Cards After Seeding", "GET", "/cards", 200)
        if success and isinstance(cards, list):
            print(f"   Successfully seeded {len(cards)} cards")
            return cards
        return []

    def test_card_crud(self):
        """Test CRUD operations for cards"""
        print("\n" + "="*60)
        print("TESTING CARD CRUD OPERATIONS")
        print("="*60)
        
        # Test card creation
        new_card = {
            "name": "Test Premium Card",
            "bank": "Test Bank",
            "min_credit_score": 700,
            "min_income": 50000,
            "annual_fee": 195,
            "reward_type": "Cashback",
            "reward_rates": [
                {"category": "Groceries", "rate": 3.0},
                {"category": "All Other", "rate": 1.0}
            ],
            "joining_bonus": 300,
            "eligibility_criteria": ["Good credit", "Stable income"],
            "hidden_charges": ["Foreign transaction fee: 3%"],
            "special_offers": ["Welcome bonus", "No annual fee first year"],
            "card_color": "#2563eb",
            "features": ["Contactless payment", "Rewards tracking"]
        }
        
        success, created_card = self.run_test("Create New Card", "POST", "/cards", 200, new_card)
        if not success:
            print("❌ Cannot test card CRUD - creation failed")
            return None
            
        card_id = created_card.get('id') if created_card else None
        if not card_id:
            print("❌ No card ID returned from creation")
            return None
            
        print(f"   Created card with ID: {card_id}")
        
        # Test card update
        updated_card = new_card.copy()
        updated_card["annual_fee"] = 0  # Make it free
        updated_card["name"] = "Test Premium Card (Updated)"
        
        self.run_test("Update Card", "PUT", f"/cards/{card_id}", 200, updated_card)
        
        # Test card deletion
        self.run_test("Delete Card", "DELETE", f"/cards/{card_id}", 200)
        
        return card_id

    def test_recommendations(self, cards):
        """Test recommendation API with AI explanations"""
        print("\n" + "="*60)
        print("TESTING AI RECOMMENDATIONS")
        print("="*60)
        
        if not cards:
            print("❌ No cards available for recommendation testing")
            return
        
        # Test user profile
        test_profile = {
            "credit_score": 750,
            "monthly_income": 60000,
            "spending_categories": [
                {"category": "Groceries", "monthly_amount": 600},
                {"category": "Dining", "monthly_amount": 400},
                {"category": "Gas", "monthly_amount": 250},
                {"category": "Travel", "monthly_amount": 300}
            ],
            "existing_cards": ["Chase Freedom"],
            "preferred_benefits": ["Travel Insurance", "No Annual Fee", "Cashback"]
        }
        
        print(f"   Testing with profile: Credit Score {test_profile['credit_score']}, Income ${test_profile['monthly_income']}")
        
        # This may take longer due to AI processing
        success, recommendations = self.run_test("Get AI Recommendations", "POST", "/recommend", 200, test_profile, timeout=45)
        
        if success and isinstance(recommendations, dict):
            recs = recommendations.get('recommendations', [])
            total_analyzed = recommendations.get('total_analyzed', 0)
            print(f"   Received {len(recs)} recommendations from {total_analyzed} cards analyzed")
            
            # Check AI explanations
            for i, rec in enumerate(recs[:3]):  # Check first 3
                ai_explanation = rec.get('ai_explanation', '')
                card_name = rec.get('card', {}).get('name', 'Unknown')
                score = rec.get('score', 0)
                eligibility = rec.get('eligibility', 'Unknown')
                
                print(f"   Recommendation {i+1}: {card_name}")
                print(f"     Score: {score}, Eligibility: {eligibility}")
                
                if ai_explanation and len(ai_explanation) > 20:
                    print(f"     AI Explanation: ✅ Generated ({len(ai_explanation)} chars)")
                    print(f"     Preview: {ai_explanation[:100]}...")
                else:
                    print(f"     AI Explanation: ❌ Missing or too short")
        
        return recommendations if success else None

    def test_comparison(self, cards):
        """Test card comparison API"""
        print("\n" + "="*60)
        print("TESTING CARD COMPARISON")
        print("="*60)
        
        if not cards or len(cards) < 2:
            print("❌ Need at least 2 cards for comparison testing")
            return
        
        # Test comparing first 3 cards
        card_ids = [card['id'] for card in cards[:3]]
        print(f"   Comparing cards: {card_ids}")
        
        success, comparison_data = self.run_test("Compare Cards", "POST", "/compare", 200, card_ids)
        
        if success and isinstance(comparison_data, list):
            print(f"   Comparison returned {len(comparison_data)} cards")
            for card in comparison_data:
                name = card.get('name', 'Unknown')
                annual_fee = card.get('annual_fee', 0)
                print(f"     {name}: ${annual_fee} annual fee")

    def test_rewards_calculation(self, cards):
        """Test rewards calculation API"""
        print("\n" + "="*60)
        print("TESTING REWARDS CALCULATION")
        print("="*60)
        
        if not cards:
            print("❌ No cards available for rewards calculation testing")
            return
        
        card_id = cards[0]['id']
        test_spending = [
            {"category": "Groceries", "amount": 500},
            {"category": "Dining", "amount": 300},
            {"category": "Gas", "amount": 200}
        ]
        
        data = {
            "card_id": card_id,
            "spending": test_spending
        }
        
        success, rewards_data = self.run_test("Calculate Rewards", "POST", "/calculate-rewards", 200, data)
        
        if success and isinstance(rewards_data, dict):
            monthly_rewards = rewards_data.get('total_monthly_rewards', 0)
            annual_rewards = rewards_data.get('total_annual_rewards', 0)
            breakdown = rewards_data.get('breakdown', [])
            
            print(f"   Monthly Rewards: ${monthly_rewards}")
            print(f"   Annual Rewards: ${annual_rewards}")
            print(f"   Breakdown: {len(breakdown)} categories")

    def test_edge_cases(self):
        """Test edge cases and error handling"""
        print("\n" + "="*60)
        print("TESTING EDGE CASES & ERROR HANDLING")
        print("="*60)
        
        # Test invalid card ID
        self.run_test("Get Non-existent Card", "GET", "/cards/invalid-id", 404)
        
        # Test invalid recommendation profile
        invalid_profile = {"invalid_field": "test"}
        self.run_test("Invalid Recommendation Profile", "POST", "/recommend", 422, invalid_profile)
        
        # Test empty comparison
        self.run_test("Empty Card Comparison", "POST", "/compare", 200, [])

    def run_all_tests(self):
        """Run complete test suite"""
        print("🚀 STARTING CREDIT CARD API COMPREHENSIVE TESTING")
        print(f"Backend URL: {self.base_url}")
        print(f"Test Time: {datetime.now().isoformat()}")
        
        # Test sequence
        self.test_basic_endpoints()
        cards = self.test_seed_cards()
        self.test_card_crud()
        recommendations = self.test_recommendations(cards)
        self.test_comparison(cards)
        self.test_rewards_calculation(cards)
        self.test_edge_cases()
        
        # Final results
        print("\n" + "="*60)
        print("TEST SUMMARY")
        print("="*60)
        print(f"Tests Run: {self.tests_run}")
        print(f"Tests Passed: {self.tests_passed}")
        print(f"Tests Failed: {self.tests_run - self.tests_passed}")
        print(f"Success Rate: {(self.tests_passed/self.tests_run)*100:.1f}%")
        
        if self.tests_passed == self.tests_run:
            print("\n🎉 ALL TESTS PASSED! Backend is working correctly.")
            return True
        else:
            print(f"\n⚠️  {self.tests_run - self.tests_passed} tests failed. Check issues above.")
            return False

def main():
    tester = CreditCardAPITester()
    success = tester.run_all_tests()
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())