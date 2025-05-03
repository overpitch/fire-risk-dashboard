# 🔥 Fire Risk Dashboard Refactoring Roadmap

## Current Status
- **Phase 0**: ✅ Initial assessment and roadmap creation (Completed)
- **Phase 1**: ✅ Project structure reorganization (Completed)
- **Phase 2**: 🔄 Best practice implementations (Partially completed)
- **Phase 3**: 🔄 Testing strategy implementation (Partially completed)
- **Phase 4**: 🔄 Documentation improvements (Partially completed)
- **Phase 4.5**: 🔄 Cache System Simplification (In progress - URGENT)
- **Phase 5**: ⏱️ Performance optimizations (Not started)
- **Phase 6**: ⏱️ Deployment improvements (Not started)
- **Phase 7**: 🔄 Admin Interface & Security Enhancements (Phase 1 completed)

---

## Phase 0: Initial Assessment and Roadmap Creation
**Status**: ✅ Completed

**Objectives**:
- Analyze the current codebase
- Identify areas for improvement
- Create a comprehensive roadmap for refactoring

**Tasks**:
- [x] Review the main.py file
- [x] Identify components that can be separated
- [x] Document best practice issues
- [x] Create this roadmap

---

## Phase 1: Project Structure Reorganization
**Status**: ✅ Completed

**Objectives**:
- Break down the monolithic app into modular components
- Create a clear directory structure
- Separate concerns (configuration, API clients, business logic, routes)

**Tasks**:
- [x] Create modular file structure
- [x] Extract configuration to config.py
  - [x] Move API keys, base URLs, and station IDs
  - [x] Implement environment variable loading
- [x] Extract API clients
  - [x] Create api_clients.py for API interactions
  - [x] Implement proper error handling and retry logic
- [x] Extract core logic
  - [x] Move DataCache class to cache.py
  - [x] Implement cache_refresh.py for refresh logic
  - [x] Move fire risk calculation to fire_risk_logic.py
- [x] Extract routes
  - [x] Implement endpoints.py for main routes
  - [x] Implement dev_endpoints.py for development routes
- [x] Set up static files directory structure
- [x] Ensure the refactored app works exactly like the original

**Completion Criteria**:
- The application is split into logical modules
- All functionality is preserved
- The application runs successfully with the new structure
- No functionality regression

---

## Phase 2: Best Practice Implementations
**Status**: 🔄 Partially completed

**Objectives**:
- Address all identified best practice issues
- Improve code quality and maintainability
- Implement modern Python and FastAPI patterns

**Tasks**:
- [x] Implement proper HTML template handling
  - [x] Set up HTML template for the dashboard
- [x] Implement consistent error handling
  - [x] Add proper error logging
  - [x] Add proper error responses
- [x] Improve configuration management
  - [x] Extract configuration to separate module
- [ ] Fix async/sync mixing
  - [ ] Replace requests with httpx for async HTTP
  - [x] Implement thread safety in cache
- [x] Enhance logging strategy
  - [x] Implement structured logging
  - [x] Configure log levels
- [x] Add type annotations
  - [x] Add types to key functions and classes
- [ ] Implement dependency injection
  - [ ] Use FastAPI's dependency injection system
- [ ] Improve API documentation
  - [ ] Add OpenAPI descriptions

**Completion Criteria**:
- All identified best practice issues are addressed
- Code quality is improved
- The application follows modern Python and FastAPI patterns
- No functionality regression

---

## Phase 3: Testing Strategy Implementation
**Status**: 🔄 Partially completed

**Objectives**:
- Add comprehensive tests
- Ensure code quality and reliability
- Prevent regression during future changes

**Tasks**:
- [x] Set up testing framework
  - [x] Add pytest and related dependencies
  - [x] Configure test settings
  - [x] Create test fixtures
- [x] Implement unit tests
  - [x] Test API clients with mocked responses
  - [x] Test cache system
  - [x] Test fire risk calculation
  - [x] Test route handlers
- [x] Implement integration tests
  - [x] Test API endpoints
  - [x] Test data flow
  - [x] Test error handling
- [x] Set up CI/CD for tests
  - [x] Add test coverage reporting
- [ ] Address test coverage gaps identified in testing.md
  - [ ] Increase test coverage for conditional branches and error handling
  - [ ] Add tests for edge cases and integration points

**Completion Criteria**:
- Comprehensive test suite is implemented
- Tests cover at least 80% of the codebase
- All tests pass
- CI/CD is set up for automated testing

---

## Phase 4: Documentation Improvements
**Status**: 🔄 Partially completed

**Objectives**:
- Improve code documentation
- Create comprehensive API documentation
- Update project documentation

**Tasks**:
- [ ] Add docstrings to all modules, classes, and functions
  - [ ] Use Google-style docstrings
  - [ ] Include type information
  - [ ] Document exceptions
- [ ] Enhance API documentation
  - [ ] Use FastAPI's built-in documentation features
  - [ ] Add examples
  - [ ] Document all endpoints
- [ ] Update README.md
  - [ ] Add detailed setup instructions
  - [ ] Document configuration options
  - [ ] Include usage examples
- [x] Create additional documentation
  - [x] Add architecture overview with [system-overview.md](system-overview.md)
  - [x] Document data flow in system overview
  - [ ] Create troubleshooting guide

**Completion Criteria**:
- All code is properly documented
- API documentation is comprehensive
- Project documentation is updated
- Documentation is accurate and helpful

---

## Phase 4.5: Cache System Simplification
**Status**: 🔄 In progress
**Priority**: URGENT (addressing critical user trust issue)

**Objectives**:
- Replace the field-by-field caching system with a simpler snapshot-based approach
- Eliminate complexity that's causing bugs and inconsistent data display
- Improve user trust by clearly indicating when data is fresh vs cached

**Tasks**:
1. **Create Git Branch** 
   - [x] Create branch `simplified-cache-approach` to preserve current implementation

2. **Refactor Data Cache Class**
   - [ ] Modify `DataCache` class to store complete snapshots instead of field-level data
   - [ ] Simplify timestamp tracking to one timestamp per snapshot
   - [ ] Remove field-level caching flags and logic
   - [ ] Add methods to store and retrieve complete snapshots

3. **Simplify Refresh Logic**
   - [ ] Modify `refresh_data_cache()` to attempt all-or-nothing updates
   - [ ] Implement clean 10-minute refresh cycle
   - [ ] Remove complex partial update and fallback logic
   - [ ] Add refresh attempt logging for monitoring

4. **Update API Response Format**
   - [ ] Modify endpoint responses to clearly indicate snapshot age
   - [ ] Add simple "fresh" or "cached" indicator to the entire response
   - [ ] Remove field-by-field cache indicators

5. **Update UI Display**
   - [ ] Add clear visual indicator when displaying cached data
   - [ ] Show single timestamp for the entire dataset
   - [ ] Ensure users understand when they're viewing historical data

6. **Testing**
   - [ ] Create tests for the new snapshot-based cache system
   - [ ] Verify regular refresh attempts work as expected
   - [ ] Test scenarios with API failures
   - [ ] Ensure UI properly displays freshness indicators

7. **Documentation**
   - [ ] Update code documentation to reflect the new approach
   - [ ] Document the snapshot-based caching strategy
   - [ ] Update any user-facing documentation about data freshness

**Completion Criteria**:
- The simplified cache system is implemented and working
- Users can clearly see when they're viewing cached data
- Regular refresh attempts occur every 10 minutes
- The system is significantly simpler and easier to maintain

---

## Phase 5: Performance Optimizations
**Status**: ⏱️ Not started

**Objectives**:
- Identify and address performance bottlenecks
- Optimize data fetching and caching
- Improve response times

**Tasks**:
- [ ] Profile the application
  - [ ] Identify slow endpoints
  - [ ] Measure response times
  - [ ] Identify memory usage patterns
- [ ] Optimize data fetching
  - [ ] Implement more efficient API clients
  - [ ] Add request batching where possible
  - [ ] Optimize concurrent requests
- [ ] Enhance caching strategy (modified to align with new snapshot-based approach)
  - [ ] Consider Redis or similar for distributed caching of snapshots
  - [ ] Optimize snapshot storage and retrieval
  - [ ] Maintain multi-station wind gust data averaging while keeping the snapshot approach
- [ ] Optimize database queries (if applicable)
  - [ ] Add indexes
  - [ ] Optimize query patterns
  - [ ] Implement connection pooling
- [ ] Implement frontend optimizations
  - [ ] Minify and bundle static assets
  - [ ] Implement lazy loading
  - [ ] Add client-side caching
  - [ ] Enhance wind gust tooltip to show data from multiple stations
  - [ ] Simplify wind gust tooltip status indicators (remove confusing checkmarks, use consistent age indicators)

**Completion Criteria**:
- Performance bottlenecks are identified and addressed
- Response times are improved
- Memory usage is optimized
- The application performs well under load
- Data resilience is improved through multi-station sampling

---

## Phase 6: Deployment Improvements
**Status**: ⏱️ Not started

**Objectives**:
- Streamline the deployment process
- Improve reliability and scalability
- Enhance monitoring and logging

**Tasks**:
- [ ] Containerize the application
  - [ ] Create Dockerfile
  - [ ] Set up docker-compose for local development
  - [ ] Optimize container size
- [ ] Improve deployment scripts
  - [ ] Update render-start.zsh
  - [ ] Add environment-specific configurations
  - [ ] Implement graceful shutdown
- [ ] Enhance monitoring
  - [ ] Add health check endpoints
  - [ ] Implement metrics collection
  - [ ] Set up alerting
- [ ] Improve logging for production
  - [ ] Configure log aggregation
  - [ ] Implement log rotation
  - [ ] Add request ID tracking

**Completion Criteria**:
- The application is containerized
- Deployment process is streamlined
- Monitoring and logging are enhanced
- The application is reliable and scalable

---

## Phase 7: Admin Interface & Security Enhancements
**Status**: 🔄 In progress

**Objectives**:
- Hide administrative functions behind a protected admin interface
- Move the Test/Normal toggle to the admin page
- Make the admin page accessible via an "Admin utilities" link
- Implement production-grade security for the admin PIN
- Prepare the admin page for future email subscriber management

**Tasks**:
1. **Initial Admin Page & Toggle Migration**
   - [x] Create admin-security.md documentation file
   - [x] Move the Test/Normal toggle from dashboard.html to admin.html
   - [x] Add "Admin utilities" link to the About Us modal footer
   - [x] Ensure PIN protection (1446) is properly implemented
   - [x] Remove current Test/Normal toggle from dashboard.html
   - [x] Test functionality to ensure the toggle works correctly

2. **Admin Security Hardening (Future Implementation)**
   - [ ] Move PIN from hardcoded values to environment variables
   - [ ] Implement proper salted password hashing with bcrypt or Argon2
   - [ ] Enhance session management and token security
   - [ ] Add configurable PIN complexity requirements
   - [ ] Implement PIN reset functionality for administrators

3. **Email Alert Testing Admin Interface (Future Implementation)**
   - [ ] Create a dedicated admin UI section for testing email alerts
   - [ ] Implement controls to simulate Orange-to-Red risk level transitions
   - [ ] Add functionality to send test emails to selected subscribers
   - [ ] Implement logging of test email activity for monitoring
   - [ ] Ensure test emails are clearly marked as test messages

4. **Email Subscriber Management Integration (Future Implementation)**
   - [ ] Integrate with the subscriber management system outlined in AWS-SES-roadmap
   - [ ] Enhance the UI for managing email subscribers
   - [ ] Implement secure API endpoints for subscriber operations
   - [ ] Add data validation for subscriber information

**Completion Criteria**:
- Admin page is accessible via "Admin utilities" link in About Us modal
- PIN protection is working securely
- Test/Normal toggle is moved from dashboard to admin page
- All functionality works correctly
- Security considerations are documented for future implementation

---

## Future Enhancements
- Implement user authentication and authorization
- Add user preferences and notifications
- Create a mobile app or responsive design
- Implement more data sources
- Add historical data analysis
- Create a public API for third-party integrations
- Expand multi-station data collection to other weather parameters

---

## How to Use This Roadmap

This roadmap is designed to be a living document that guides the refactoring process. Each phase has clear objectives, tasks, and completion criteria. As we complete each phase, we'll update the "Current Status" section at the top of the document.

To work on the next phase, simply ask to "work on the next phase of the roadmap" or specify a particular phase you'd like to focus on. The roadmap is detailed enough that you don't need to provide additional context.

After each phase is completed, we'll update this roadmap to reflect the progress and any changes to the plan.

## Environment Setup Requirements

**⚠️ CRITICAL: ALWAYS ENSURE VIRTUAL ENVIRONMENT IS ACTIVE BEFORE EXECUTING COMMANDS ⚠️**

Before running any Python commands or installing any packages, ensure the virtual environment is active by checking for the `(venv)` prefix in your terminal prompt.

If the virtual environment is not active, activate it:

```bash
# On macOS/Linux
source venv/bin/activate

# On Windows
.\venv\Scripts\activate
```

Never run Python commands or install packages outside the project's virtual environment.

### Command Execution Checklist
- [ ] Virtual environment is active
- [ ] Working in the correct directory
- [ ] Required dependencies are installed
