# Description
This is a requirements description for an application that searches job boards
and employer sites for individual job offers.
# Problem statement
Workers are wasting time on searching for a job offers that are not matched or not active.
# Vision
The main goal is to help employees to find a job as fast as possible. 
# Main flow
- log in with Google Account or create a account
- load CV in PDF
- provide additional criteria
- choose a pricing plan: free or premium
- execute job searching
- preview results

# Use Cases
## Upload CV in PDF
Preconditions:
- this feature is available only for Premium Plan
- user should be logged in

Scenario:
- upload CV - User
- analyse CV - AI Agent
- update and accept your profile in terms of technical and non-technical skills you have - User

## Update Profile
Preconditions:
- user should be logged in

Scenario:
- get to User Profile - User
- update Core criteria - User
- update other criteraa - User
- accept - User

## Search for job offers
Preconditions:
- User Profile should be prepared
- when a user has available credits, use the configured low-cost validation
  model; an exhausted Free account uses deterministic content checks without
  incurring additional AI debt

Scenario:
- click Search - User
- analyse User Profile and prepare request - AI Agent
- execute request - AI Agent
- display results - AI Agent
- click job offer that is open in new browser tab  -User

# Requirements
- user should be able to create its own profile by loading CV in PDF which is then analysed by ai model to collect skills and language 
- user should be able to update its profile manually
- user should be able to load list of companies that are out of his interest
- costs of tokens should be registered to have a current cost per user tracked
- non-technical search criteria that are provided by user: area (like country or city), work type (exactly remote, on-site, or hybrid), salary required, agreement type (b2b contract, labor agreement)
- other search criteria should be taken by default from a user profile

# Architecture
## Job Offers Request
Before app executes request for jobs it should prepare a criteria. As fitting all user skills and criteria is not possible or would be limited to the only few job offers it should be a core criteria that job offer should match. Other criteria should be used for sorting to let user find most accurate jobs at the top of the list.
Limit job offers to only active ones if possible.

## Job Offers Response
As a result it should sorted list presented. The main part of list item should be a link to job offer.
List should not present a non active jobs.

## Job listing
It should implement sorting strategy according to the following criteria: skills matching, non-technical criteria matching

# Pricing
## Free
- new users start on Free
- user can run two searches with up to 5 job offers each
- user can upload a CV; local extraction is used when AI credits are unavailable
- search requests are queued and run on schedule
- results are sent on email
- there should be a delay for executing next request (configurable parameter, 1h by default)
## Premium
- a 2 EUR purchase adds 4 credits and restores Premium
- balance is tracked as append-only purchase and actual AI usage events
- AI USD cost is converted using the current EUR/USD rate and multiplied by
  the configurable credit-cost multiplier (default 10)
- payment method is Przelewy24 and BLIK
- results are presented on the screen
- user gets up to 10 job offers
- when costs reach 50% of fee then ai model from Free plan should be used

# Technical stack
- Python
- Tavily for multi-source job searching
- LangChain - AI infrastructure
- LangSmith - monitoring
- CopilotKit framework
- SQLite storage for the local proof of concept

# Implemented product scope
- FastAPI backend with a Next.js website
- authenticated email/password accounts and optional Google OAuth
- optional seeded demo users for local development only
- Premium users can upload a PDF CV for profile extraction
- live multi-source job discovery is performed through Tavily
- LinkedIn offers receive direct-page validation; other individual offer URLs
  are canonicalized and validated from extracted source content
- job offers are deduplicated and ranked by core skills, location, work mode, and contract type
- CopilotKit provides an embedded assistant for refining search criteria
- Free searches are queued, rate-limited, run by a protected scheduled worker,
  and delivered through SMTP
- Premium upgrades use the Przelewy24 hosted checkout and support BLIK
- production deployment uses separate frontend and API containers with one
  persistent SQLite volume attached to a single API instance
