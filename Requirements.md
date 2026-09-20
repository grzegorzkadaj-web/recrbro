# Description
This a requirements description for aplication which searches throught LinkedIn for job offers.
# Problem statement
Workers are wasting time on searching for a job offers that are not matched or not active.
# Vision
The main goal is to help employees to find a job as fast as possible. 
# Main Use Case
- log in with Google Account or create a account
- load CV in PDF
- provide additional criteria
- choose a pricing plan: free or premium
- execute job searching
- preview results

# Requirements
- user should be able to create its own profile by loading CV in PDF which is then analysed by ai model to collect skills and language 
- user should be able to update its profile manually4
- user should be able to load list of companies that are out of his interest
- costs of tokens should be registered to have a current cost per user tracked
- non-technical search criteria that are provided by user: area (like country or city), work type (remote, on-site, hybryd), salary required, agreement type (b2b contract, labor agreement)
- other search criteria should be taken by default from a user profile

# Pricing
## Free
- user gets 5 job offers
- the cheapest model is used for processing a offers
- search requests are queued and run on schedule
- results are sent on email
- there should be a delay for executing next request (configurable parameter, 1h by default)
## Premium
- fee is 50 PLN
- payment method is Przelewy24 and BLIK
- results are presented on the screen
- user gets up to 100 job offer
- when costs reach 50% of fee then ai model from Free plan should be used

# Technical stack
- Python
- Tavily for LinkedIn searching
- LangChain - AI infrastructure
- LangSmith - monitoring
- CopilotKit framework
- storage ???
