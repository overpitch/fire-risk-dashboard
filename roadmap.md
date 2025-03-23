# 🔥 Fire Risk Dashboard Roadmap

## Current Status
- **Phase 0**: ✅ Initial assessment and roadmap creation
- **Phase 1**: 🔄 "What if?" Threshold Simulation Feature - Addressing regressions and bugs

## Current Focus: Bug Fixes and Regressions

**High Priority:**
- Restore core dashboard functionality (data fetching, caching, display)
- Fix "Can't find variable: $" error in "What If?" modal

**Medium Priority:**
- Address regressions in assessment colors, caching behavior, and threshold displays

**Low Priority:**
- General roadmap updates and future enhancements


---


---

## Phase 0: Initial Assessment and Roadmap Creation
**Status**: ✅ Completed

**Objectives**:
- Analyze the current codebase
- Identify areas for improvement
- Create a comprehensive roadmap for feature enhancement

**Tasks**:
- [x] Review the main.py file
- [x] Identify components that can be separated
- [x] Document best practice issues
- [x] Create this roadmap

---

## Phase 1: "What if?" Threshold Simulation Feature
**Status**: ✅ Completed

**Objectives**:
- Add ability for users to experiment with different environmental thresholds
- Show how threshold adjustments affect fire risk assessment
- Provide intuitive UI for threshold manipulation
- Allow users to compare actual vs. simulated risk

**Tasks**:
- [x] Backend Changes:
  - [x] Add new `/simulate-fire-risk` endpoint
  - [x] Implement `calculate_fire_risk` function to accept custom thresholds
  - [x] Ensure proper error handling for invalid threshold values
  
- [x] Frontend Changes:
  - [x] Add "What if?" button beside existing "Refresh Data" button
  - [x] Create Bootstrap modal dialog for threshold adjustment
  - [x] Implement sliders/inputs for each threshold with default values
  - [x] Add JavaScript to handle the simulation request and response:
    - [x] Implement `openWhatIfModal()`
    - [x] Implement `runSimulation()`
    - [x] Implement `displaySimulationResults()`
    - [x] Implement `resetSimulation()`
  - [x] Create clear visual indicators for simulation mode
  
- [ ] User Experience Improvements:
  - [ ] Add tooltips explaining threshold meanings
  - [ ] Show visual feedback when thresholds are exceeded
  - [ ] Display comparison between actual and simulated risk
  - [ ] Add reset functionality to exit simulation mode
  
- [ ] Testing:
  - [ ] Test the new endpoint with various threshold combinations
  - [ ] Verify UI works correctly across different browsers
  - [ ] Ensure proper error handling for edge cases

**Completion Criteria**:
- Users can click "What if?" button to enter simulation mode
- Users can adjust all five threshold values
- System displays simulated fire risk based on custom thresholds
- Clear visual indicators show when simulation mode is active
- Users can easily exit simulation mode

---

## Appendix: Candidate Enhancements

*These items represent potential future enhancements that may be moved into the active roadmap as priorities dictate.*

### Project Structure Reorganization

**Objectives**:
- Break down the monolithic app into modular components
- Create a clear directory structure
- Separate concerns (configuration, API clients, business logic, routes)

**Tasks**:
- Create a modular directory structure
- Extract configuration to config.py
- Extract API clients to separate modules
- Extract core logic to separate modules
- Extract routes to separate modules
- Extract HTML template
- Update main.py to import and use the new modules

### Best Practice Implementations

**Objectives**:
- Address identified best practice issues
- Improve code quality and maintainability
- Implement modern Python and FastAPI patterns

**Tasks**:
- Implement proper HTML template handling
- Implement consistent error handling
- Improve configuration management
- Fix async/sync mixing
- Enhance logging strategy
- Add comprehensive type annotations
- Implement dependency injection
- Improve API documentation

### Testing Strategy Implementation

**Objectives**:
- Add comprehensive tests
- Ensure code quality and reliability
- Prevent regression during future changes

**Tasks**:
- Set up testing framework
- Implement unit tests
- Implement integration tests
- Set up CI/CD for tests

### Documentation Improvements

**Objectives**:
- Improve code documentation
- Create comprehensive API documentation
- Update project documentation

**Tasks**:
- Add docstrings to all modules, classes, and functions
- Enhance API documentation
- Update README.md
- Create additional documentation

### Performance Optimizations

**Objectives**:
- Identify and address performance bottlenecks
- Optimize data fetching and caching
- Improve response times

**Tasks**:
- Profile the application
- Optimize data fetching
- Enhance caching strategy
- Optimize database queries (if applicable)
- Implement frontend optimizations

### Deployment Improvements

**Objectives**:
- Streamline the deployment process
- Improve reliability and scalability
- Enhance monitoring and logging

**Tasks**:
- Containerize the application
- Improve deployment scripts
- Enhance monitoring
- Improve logging for production

---

## How to Use This Roadmap

This roadmap is designed to be a living document that guides the development process. Each phase has clear objectives, tasks, and completion criteria. As we complete each phase, we'll update the "Current Status" section at the top of the document.

Priority items are included in the main roadmap, while potential future enhancements are listed in the Appendix. Items will be moved from the Appendix to the main roadmap as priorities dictate.
**Status**: ⏱️ Not started

**Objectives**:
- Address all identified best practice issues
- Improve code quality and maintainability
- Implement modern Python and FastAPI patterns

**Tasks**:
- [ ] Implement proper HTML template handling
  - [ ] Set up Jinja2 Templates with FastAPI
  - [ ] Create base templates and components
  - [ ] Move JavaScript to separate files
- [ ] Implement consistent error handling
  - [ ] Create custom exception classes
  - [ ] Implement error middleware
  - [ ] Add proper error responses
- [ ] Improve configuration management
  - [ ] Use Pydantic settings for all configuration
  - [ ] Implement configuration validation
  - [ ] Add environment-specific configurations
- [ ] Fix async/sync mixing
  - [ ] Replace requests with httpx for async HTTP
  - [ ] Ensure proper async patterns throughout
  - [ ] Fix thread safety issues in cache
- [ ] Enhance logging strategy
  - [ ] Implement structured logging
  - [ ] Add log rotation
  - [ ] Configure log levels
- [ ] Add comprehensive type annotations
  - [ ] Add types to all functions and classes
  - [ ] Create type aliases for complex types
  - [ ] Use generics where appropriate
- [ ] Implement dependency injection
  - [ ] Use FastAPI's dependency injection system
  - [ ] Create service classes for business logic
  - [ ] Make dependencies explicit
- [ ] Improve API documentation
  - [ ] Add OpenAPI descriptions
  - [ ] Create response models
  - [ ] Document all parameters

**Completion Criteria**:
- All identified best practice issues are addressed
- Code quality is improved
- The application follows modern Python and FastAPI patterns
- No functionality regression

---

## Phase 3: Testing Strategy Implementation
**Status**: ⏱️ Not started

**Objectives**:
- Add comprehensive tests
- Ensure code quality and reliability
- Prevent regression during future changes

**Tasks**:
- [ ] Set up testing framework
  - [ ] Add pytest and related dependencies
  - [ ] Configure test settings
  - [ ] Create test fixtures
- [ ] Implement unit tests
  - [ ] Test API clients with mocked responses
  - [ ] Test cache system
  - [ ] Test fire risk calculation
  - [ ] Test route handlers
- [ ] Implement integration tests
  - [ ] Test API endpoints
  - [ ] Test data flow
  - [ ] Test error handling
- [ ] Set up CI/CD for tests
  - [ ] Configure GitHub Actions or similar
  - [ ] Add test coverage reporting
  - [ ] Implement pre-commit hooks

**Completion Criteria**:
- Comprehensive test suite is implemented
- Tests cover at least 80% of the codebase
- All tests pass
- CI/CD is set up for automated testing

---

## Phase 4: Documentation Improvements
**Status**: ⏱️ Not started

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
- [ ] Create additional documentation
  - [ ] Add architecture overview
  - [ ] Document data flow
  - [ ] Create troubleshooting guide

**Completion Criteria**:
- All code is properly documented
- API documentation is comprehensive
- Project documentation is updated
- Documentation is accurate and helpful

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
- [ ] Enhance caching strategy
  - [ ] Implement more efficient cache invalidation
  - [ ] Add Redis or similar for distributed caching
  - [ ] Optimize cache key generation
- [ ] Optimize database queries (if applicable)
  - [ ] Add indexes
  - [ ] Optimize query patterns
  - [ ] Implement connection pooling
- [ ] Implement frontend optimizations
  - [ ] Minify and bundle static assets
  - [ ] Implement lazy loading
  - [ ] Add client-side caching

**Completion Criteria**:
- Performance bottlenecks are identified and addressed
- Response times are improved
- Memory usage is optimized
- The application performs well under load

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

## Future Enhancements
- Implement user authentication and authorization
- Add user preferences and notifications
- Create a mobile app or responsive design
- Implement more data sources
- Add historical data analysis
- Create a public API for third-party integrations

---

## How to Use This Roadmap

This roadmap is designed to be a living document that guides the refactoring process. Each phase has clear objectives, tasks, and completion criteria. As we complete each phase, we'll update the "Current Status" section at the top of the document.

To work on the next phase, simply ask to "work on the next phase of the roadmap" or specify a particular phase you'd like to focus on. The roadmap is detailed enough that you don't need to provide additional context.

After each phase is completed, we'll update this roadmap to reflect the progress and any changes to the plan.
