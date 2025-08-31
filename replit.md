# BotFactory - AI Chatbot Platform

## Overview

BotFactory is a SaaS platform that enables businesses to create and deploy intelligent AI chatbots powered by Google Gemini. Users can build custom chatbots for Telegram and other platforms by uploading knowledge bases and configuring bot personalities without requiring coding skills. The platform offers subscription-based access with tiered features for different business needs.

## User Preferences

Preferred communication style: Simple, everyday language in Uzbek.

## Admin Credentials
- Username: Akramjon
- Password: Gisobot20141920*
- Email: akramjon@botfactory.com

## System Architecture

### Web Framework Architecture
- **Flask-based MVC Architecture**: Uses Flask as the primary web framework with Blueprint-based routing for modular organization
- **Template Engine**: Jinja2 templating with Bootstrap 5 for responsive UI components
- **Session Management**: Flask-Login for user authentication and session handling
- **Static Assets**: CSS/JS served through Flask's static file handling

### Database Architecture
- **SQLAlchemy ORM**: Database abstraction layer with declarative models
- **Migration Support**: Flask-Migrate for database schema versioning
- **Model Structure**: Core entities include User, Bot, Subscription, KnowledgeBase, Conversation, and Message
- **Relationship Design**: One-to-many relationships between users and bots, bots and conversations, with proper foreign key constraints

### Service Layer Architecture
- **AuthService**: Handles user authentication, registration, and account management
- **AIService**: Integrates with Google Gemini API for AI-powered responses using system prompts and knowledge base context
- **TelegramService**: Manages Telegram bot instances with polling threads and webhook handling

### Authentication & Authorization
- **User Management**: Username/password authentication with bcrypt password hashing
- **Session Security**: Secure session handling with configurable secret keys
- **Access Control**: Login-required decorators for protected routes

### AI Integration Design
- **Google Gemini Integration**: Uses Google Generative AI SDK for natural language processing
- **Context Management**: Combines bot system prompts with knowledge base entries for contextual responses
- **Knowledge Base**: File upload system supporting text documents with content indexing

### Subscription Management
- **Tiered Plans**: Free, Basic, and Premium subscription levels with different bot and message limits
- **Usage Tracking**: Monitors bot creation limits and monthly message quotas
- **Automatic Provisioning**: Creates default free subscriptions for new users

## External Dependencies

### AI Services
- **Google Gemini API**: Core AI service for generating chatbot responses using gemini-2.5-flash model
- **API Authentication**: Requires GEMINI_API_KEY environment variable

### Messaging Platforms
- **Telegram Bot API**: Integration for deploying bots to Telegram using python-telegram-bot library
- **Bot Token Management**: Validates and manages Telegram bot tokens for multiple bot instances

### Database Systems
- **SQLite**: Default development database with configurable DATABASE_URL
- **PostgreSQL Ready**: Architecture supports PostgreSQL for production deployments

### Frontend Dependencies
- **Bootstrap 5**: UI framework with dark theme support via Replit CDN
- **Font Awesome**: Icon library for UI components
- **jQuery**: JavaScript utilities for enhanced interactivity

### Infrastructure Services
- **File Upload Handling**: Support for knowledge base document uploads with size limits
- **Proxy Support**: ProxyFix middleware for deployment behind reverse proxies
- **Environment Configuration**: Configurable via environment variables for secrets and database URLs

### Python Libraries
- **Flask Ecosystem**: Flask, Flask-SQLAlchemy, Flask-Migrate, Flask-Login
- **Security**: Werkzeug for password hashing and secure filename handling
- **Telegram**: python-telegram-bot for bot management
- **AI**: google-generativeai for Gemini integration