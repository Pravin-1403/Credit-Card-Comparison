from fastapi import FastAPI, APIRouter, HTTPException
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict
import uuid
from datetime import datetime, timezone
#from emergentintegrations.llm.chat import LlmChat, UserMessage

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Create the main app without a prefix
app = FastAPI()
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def home():
     return {"message": "Backend is working 🚀"}
# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# Models
class RewardRate(BaseModel):
    category: str
    rate: float

class CreditCard(BaseModel):
    model_config = ConfigDict(extra="ignore")
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    bank: str
    min_credit_score: int
    min_income: float
    annual_fee: float
    reward_type: str
    reward_rates: List[RewardRate]
    joining_bonus: float
    eligibility_criteria: List[str]
    hidden_charges: List[str]
    special_offers: List[str]
    image_url: Optional[str] = None
    card_color: str = "#1e293b"
    features: List[str] = []
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class CreditCardCreate(BaseModel):
    name: str
    bank: str
    min_credit_score: int
    min_income: float
    annual_fee: float
    reward_type: str
    reward_rates: List[RewardRate]
    joining_bonus: float
    eligibility_criteria: List[str]
    hidden_charges: List[str]
    special_offers: List[str]
    image_url: Optional[str] = None
    card_color: str = "#1e293b"
    features: List[str] = []

class SpendingCategory(BaseModel):
    category: str
    monthly_amount: float

class UserProfile(BaseModel):
    credit_score: int
    monthly_income: float
    spending_categories: List[SpendingCategory]
    existing_cards: List[str]
    preferred_benefits: List[str]

class CardRecommendation(BaseModel):
    card: CreditCard
    score: float
    eligibility: str
    estimated_monthly_rewards: float
    ai_explanation: str
    pros: List[str]
    cons: List[str]
    risk_alerts: List[str]

class RecommendationResponse(BaseModel):
    recommendations: List[CardRecommendation]
    total_analyzed: int

# Routes
@api_router.get("/")
async def root():
    return {"message": "Credit Card Recommendation API"}

@api_router.post("/cards", response_model=CreditCard)
async def create_card(card_data: CreditCardCreate):
    card = CreditCard(**card_data.model_dump())
    doc = card.model_dump()
    doc['created_at'] = doc['created_at'].isoformat()
    doc['reward_rates'] = [r.model_dump() for r in card.reward_rates]
    
    await db.credit_cards.insert_one(doc)
    return card

@api_router.get("/cards", response_model=List[CreditCard])
async def get_cards(
    reward_type: Optional[str] = None,
    min_score: Optional[int] = None,
    lifetime_free: Optional[bool] = None
):
    query = {}
    if reward_type:
        query['reward_type'] = reward_type
    if min_score:
        query['min_credit_score'] = {'$lte': min_score}
    if lifetime_free is not None and lifetime_free:
        query['annual_fee'] = 0
    
    cards = await db.credit_cards.find(query, {"_id": 0}).to_list(1000)
    
    for card in cards:
        if isinstance(card.get('created_at'), str):
            card['created_at'] = datetime.fromisoformat(card['created_at'])
    
    return cards

@api_router.delete("/cards/{card_id}")
async def delete_card(card_id: str):
    result = await db.credit_cards.delete_one({"id": card_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Card not found")
    return {"message": "Card deleted successfully"}

@api_router.put("/cards/{card_id}", response_model=CreditCard)
async def update_card(card_id: str, card_data: CreditCardCreate):
    card = CreditCard(id=card_id, **card_data.model_dump())
    doc = card.model_dump()
    doc['created_at'] = doc['created_at'].isoformat()
    doc['reward_rates'] = [r.model_dump() for r in card.reward_rates]
    
    result = await db.credit_cards.replace_one({"id": card_id}, doc)
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Card not found")
    return card

def calculate_card_score(card: CreditCard, profile: UserProfile) -> tuple[float, float]:
    score = 0.0
    estimated_rewards = 0.0
    
    # Calculate rewards match (40% weight)
    reward_match_score = 0.0
    for spending in profile.spending_categories:
        for reward_rate in card.reward_rates:
            if reward_rate.category.lower() in spending.category.lower() or spending.category.lower() in reward_rate.category.lower():
                reward_match_score += reward_rate.rate * spending.monthly_amount
                estimated_rewards += (reward_rate.rate / 100) * spending.monthly_amount
    
    score += (reward_match_score / 100) * 0.4
    
    # Fee vs benefit ratio (30% weight)
    annual_benefit = estimated_rewards * 12 + card.joining_bonus
    if card.annual_fee == 0:
        fee_benefit_score = 100
    else:
        fee_benefit_score = min(100, (annual_benefit / card.annual_fee) * 20)
    
    score += fee_benefit_score * 0.3
    
    # Preferred benefits match (20% weight)
    benefits_match = 0
    for pref in profile.preferred_benefits:
        if any(pref.lower() in offer.lower() for offer in card.special_offers):
            benefits_match += 1
    if len(profile.preferred_benefits) > 0:
        score += (benefits_match / len(profile.preferred_benefits)) * 100 * 0.2
    
    # Credit score buffer (10% weight)
    score_buffer = profile.credit_score - card.min_credit_score
    score += min(100, max(0, score_buffer / 2)) * 0.1
    
    return round(score, 2), round(estimated_rewards, 2)

def predict_eligibility(card: CreditCard, profile: UserProfile) -> str:
    score_diff = profile.credit_score - card.min_credit_score
    income_ratio = profile.monthly_income / card.min_income if card.min_income > 0 else 2
    
    if score_diff >= 100 and income_ratio >= 1.5:
        return "High"
    elif score_diff >= 50 and income_ratio >= 1.2:
        return "Medium"
    elif score_diff >= 0 and income_ratio >= 1.0:
        return "Low"
    else:
        return "Not Eligible"

async def generate_ai_explanation(card: CreditCard, profile: UserProfile, score: float, estimated_rewards: float) -> str:
    try:
        llm_key = os.environ.get('EMERGENT_LLM_KEY')
        if not llm_key:
            return "AI explanation unavailable. Please configure EMERGENT_LLM_KEY."
        
        chat = LlmChat(
            api_key=llm_key,
            session_id=f"card_rec_{uuid.uuid4()}",
            system_message="You are a financial advisor explaining credit card recommendations. Be concise, helpful, and focus on why this card matches the user's profile."
        ).with_model("openai", "gpt-5.2")
        
        prompt = f"""Explain in 2-3 sentences why {card.name} by {card.bank} is recommended for this user:

User Profile:
- Credit Score: {profile.credit_score}
- Monthly Income: ${profile.monthly_income:,.0f}
- Top Spending: {', '.join([s.category for s in profile.spending_categories[:3]])}
- Preferences: {', '.join(profile.preferred_benefits)}

Card Details:
- Reward Type: {card.reward_type}
- Annual Fee: ${card.annual_fee}
- Joining Bonus: ${card.joining_bonus}
- Match Score: {score}/100
- Est. Monthly Rewards: ${estimated_rewards}

Be specific about reward matches and value proposition."""
        
        message = UserMessage(text=prompt)
        response = await chat.send_message(message)
        return response.strip()
    except Exception as e:
        logging.error(f"AI explanation error: {e}")
        return f"This card scores {score}/100 for your profile with estimated monthly rewards of ${estimated_rewards}."

def analyze_card(card: CreditCard, profile: UserProfile) -> tuple[List[str], List[str], List[str]]:
    pros = []
    cons = []
    risks = []
    
    # Pros
    if card.annual_fee == 0:
        pros.append("Lifetime free card - no annual fee")
    if card.joining_bonus > 0:
        pros.append(f"Welcome bonus of ${card.joining_bonus:,.0f}")
    if len(card.special_offers) > 0:
        pros.append(f"{len(card.special_offers)} special offers available")
    
    # Cons
    if card.annual_fee > 500:
        cons.append(f"High annual fee of ${card.annual_fee:,.0f}")
    if card.min_credit_score > profile.credit_score + 50:
        cons.append("Credit score requirement may be challenging")
    
    # Risks
    if len(card.hidden_charges) > 0:
        risks.append(f"Hidden charges: {', '.join(card.hidden_charges[:2])}")
    if card.annual_fee > 1000:
        risks.append("Premium card with significant annual fee")
    
    return pros, cons, risks

@api_router.post("/recommend", response_model=RecommendationResponse)
async def recommend_cards(profile: UserProfile):
    # Get all eligible cards
    cards = await db.credit_cards.find(
        {
            "min_credit_score": {"$lte": profile.credit_score},
            "min_income": {"$lte": profile.monthly_income}
        },
        {"_id": 0}
    ).to_list(1000)
    
    if not cards:
        return RecommendationResponse(recommendations=[], total_analyzed=0)
    
    # Convert to CreditCard objects
    card_objects = []
    for card_data in cards:
        if isinstance(card_data.get('created_at'), str):
            card_data['created_at'] = datetime.fromisoformat(card_data['created_at'])
        card_objects.append(CreditCard(**card_data))
    
    # Score and rank cards
    recommendations = []
    for card in card_objects:
        score, estimated_rewards = calculate_card_score(card, profile)
        eligibility = predict_eligibility(card, profile)
        
        if eligibility == "Not Eligible":
            continue
        
        ai_explanation = await generate_ai_explanation(card, profile, score, estimated_rewards)
        pros, cons, risks = analyze_card(card, profile)
        
        recommendations.append(CardRecommendation(
            card=card,
            score=score,
            eligibility=eligibility,
            estimated_monthly_rewards=estimated_rewards,
            ai_explanation=ai_explanation,
            pros=pros,
            cons=cons,
            risk_alerts=risks
        ))
    
    # Sort by score
    recommendations.sort(key=lambda x: x.score, reverse=True)
    
    # Return top recommendations
    return RecommendationResponse(
        recommendations=recommendations[:10],
        total_analyzed=len(card_objects)
    )

@api_router.post("/compare")
async def compare_cards(card_ids: List[str]):
    cards = await db.credit_cards.find(
        {"id": {"$in": card_ids}},
        {"_id": 0}
    ).to_list(100)
    
    for card in cards:
        if isinstance(card.get('created_at'), str):
            card['created_at'] = datetime.fromisoformat(card['created_at'])
    
    return cards

@api_router.post("/calculate-rewards")
async def calculate_rewards(data: dict):
    card_id = data.get('card_id')
    spending = data.get('spending', [])
    
    card = await db.credit_cards.find_one({"id": card_id}, {"_id": 0})
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")
    
    total_rewards = 0.0
    breakdown = []
    
    for spend in spending:
        category = spend['category']
        amount = spend['amount']
        
        # Find matching reward rate
        reward_rate = 0
        for rate in card['reward_rates']:
            if rate['category'].lower() in category.lower() or category.lower() in rate['category'].lower():
                reward_rate = rate['rate']
                break
        
        rewards = (reward_rate / 100) * amount
        total_rewards += rewards
        breakdown.append({
            'category': category,
            'amount': amount,
            'rate': reward_rate,
            'rewards': round(rewards, 2)
        })
    
    return {
        'total_monthly_rewards': round(total_rewards, 2),
        'total_annual_rewards': round(total_rewards * 12, 2),
        'breakdown': breakdown
    }

# Seed initial data
@api_router.post("/seed-cards")
async def seed_cards():
    existing = await db.credit_cards.count_documents({})
    if existing > 0:
        return {"message": "Cards already seeded"}
    
    sample_cards = [
        CreditCardCreate(
            name="Emerald Cashback Elite",
            bank="First National Bank",
            min_credit_score=700,
            min_income=50000,
            annual_fee=0,
            reward_type="Cashback",
            reward_rates=[
                RewardRate(category="Groceries", rate=3.0),
                RewardRate(category="Dining", rate=2.0),
                RewardRate(category="Gas", rate=2.0),
                RewardRate(category="All Other", rate=1.0)
            ],
            joining_bonus=200,
            eligibility_criteria=["Good credit score", "Stable income"],
            hidden_charges=["Foreign transaction fee: 3%"],
            special_offers=["No annual fee for life", "5% cashback on first 3 months"],
            card_color="#047857",
            features=["No annual fee", "Welcome bonus", "Grocery rewards"]
        ),
        CreditCardCreate(
            name="Platinum Travel Rewards",
            bank="Global Trust Bank",
            min_credit_score=750,
            min_income=75000,
            annual_fee=495,
            reward_type="Travel",
            reward_rates=[
                RewardRate(category="Travel", rate=5.0),
                RewardRate(category="Dining", rate=3.0),
                RewardRate(category="All Other", rate=1.0)
            ],
            joining_bonus=750,
            eligibility_criteria=["Excellent credit", "High income"],
            hidden_charges=["Balance transfer fee: 3%", "Late payment: $40"],
            special_offers=["Airport lounge access", "Travel insurance", "No foreign transaction fees"],
            card_color="#475569",
            features=["Travel insurance", "Lounge access", "5x travel points"]
        ),
        CreditCardCreate(
            name="Smart Student Card",
            bank="Education Finance Corp",
            min_credit_score=600,
            min_income=15000,
            annual_fee=0,
            reward_type="Cashback",
            reward_rates=[
                RewardRate(category="Streaming", rate=5.0),
                RewardRate(category="Dining", rate=3.0),
                RewardRate(category="All Other", rate=1.0)
            ],
            joining_bonus=50,
            eligibility_criteria=["Student status", "Basic credit history"],
            hidden_charges=["Cash advance fee: $10 or 5%"],
            special_offers=["No annual fee", "Build credit history", "Student discounts"],
            card_color="#0ea5e9",
            features=["No annual fee", "Student friendly", "Streaming rewards"]
        ),
        CreditCardCreate(
            name="Premium Rewards Gold",
            bank="Prestige Banking",
            min_credit_score=720,
            min_income=60000,
            annual_fee=195,
            reward_type="Points",
            reward_rates=[
                RewardRate(category="Shopping", rate=4.0),
                RewardRate(category="Entertainment", rate=3.0),
                RewardRate(category="All Other", rate=2.0)
            ],
            joining_bonus=500,
            eligibility_criteria=["Good to excellent credit", "Regular spending"],
            hidden_charges=["Foreign transaction fee: 2.5%", "Cash advance: 5%"],
            special_offers=["Extended warranty", "Purchase protection", "Concierge service"],
            card_color="#d97706",
            features=["Purchase protection", "Concierge service", "Flexible redemption"]
        ),
        CreditCardCreate(
            name="Business Pro Card",
            bank="Commerce Bank",
            min_credit_score=680,
            min_income=40000,
            annual_fee=99,
            reward_type="Cashback",
            reward_rates=[
                RewardRate(category="Office Supplies", rate=5.0),
                RewardRate(category="Gas", rate=3.0),
                RewardRate(category="All Other", rate=1.5)
            ],
            joining_bonus=300,
            eligibility_criteria=["Business owner", "Fair credit"],
            hidden_charges=["Late fee: $35"],
            special_offers=["Employee cards at no cost", "Expense management tools", "Business insurance"],
            card_color="#1e293b",
            features=["Business tools", "Employee cards", "Expense tracking"]
        ),
        CreditCardCreate(
            name="Fuel Saver Card",
            bank="Energy Bank",
            min_credit_score=650,
            min_income=30000,
            annual_fee=0,
            reward_type="Fuel",
            reward_rates=[
                RewardRate(category="Gas", rate=5.0),
                RewardRate(category="Groceries", rate=2.0),
                RewardRate(category="All Other", rate=1.0)
            ],
            joining_bonus=100,
            eligibility_criteria=["Fair credit", "Regular driver"],
            hidden_charges=["Cash advance: $10 or 5%"],
            special_offers=["5% cashback at partner stations", "No annual fee"],
            card_color="#dc2626",
            features=["5% gas rewards", "No annual fee", "Partner station network"]
        )
    ]
    
    for card_data in sample_cards:
        card = CreditCard(**card_data.model_dump())
        doc = card.model_dump()
        doc['created_at'] = doc['created_at'].isoformat()
        doc['reward_rates'] = [r.model_dump() for r in card.reward_rates]
        await db.credit_cards.insert_one(doc)
    
    return {"message": f"Seeded {len(sample_cards)} credit cards"}

# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()


