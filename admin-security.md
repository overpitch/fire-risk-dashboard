# Admin Interface & Security Enhancement Plan

This document outlines the plan for enhancing the admin interface and security measures for the Fire Risk Dashboard.

## Current State

- The dashboard.html page has a Test/Normal toggle directly in the navigation bar
- There's an existing admin.html page with PIN protection (PIN=1446)
- The admin page includes test mode toggle and subscriber management functionality
- Basic PIN protection exists with some security measures (rate limiting, basic hashing)

## Goals

1. Hide administrative functions behind a protected admin interface
2. Move the Test/Normal toggle to the admin page
3. Make the admin page accessible via an "Admin utilities" link in the About Us dialog
4. Implement production-grade security for the admin PIN
5. Prepare the admin page for future email subscriber management

## Implementation Plan

### Phase 1: Initial Admin Page & Toggle Migration (Current Task)

- [x] Create this documentation file
- [x] Move the Test/Normal toggle from dashboard.html to admin.html (already exists there)
- [x] Add "Admin utilities" link to the About Us modal footer
- [x] Ensure PIN protection (1446) is properly implemented
- [x] Remove current Test/Normal toggle from dashboard.html
- [x] Test functionality to ensure the toggle works correctly in admin.html

### Phase 2: Admin Security Hardening (Future Task)

- [ ] Move PIN from hardcoded values to environment variables
- [ ] Implement proper salted password hashing with bcrypt or Argon2
- [ ] Enhance session management
  - [ ] Implement secure session token generation and validation
  - [ ] Add proper session expiration handling
  - [ ] Protect against session fixation attacks
- [ ] Add configurable PIN complexity requirements
- [ ] Implement PIN reset functionality for administrators

### Phase 3: Email Subscriber Management (Future Task)

- [ ] Integrate the admin page with the subscriber management system
- [ ] Enhance the UI for managing email subscribers
- [ ] Implement secure API endpoints for subscriber operations
- [ ] Add data validation for subscriber information
- [ ] Implement export and import functionality for subscriber lists

## Security Considerations

The current PIN system has several security weaknesses that will be addressed in Phase 2:

1. **Hardcoded PINs**: The PIN (1446) is currently hardcoded in both client and server code.
   - Risk: Anyone with access to the code can see the PIN.
   - Mitigation: Move PIN to environment variables and use proper secure storage.

2. **Weak Hashing**: The current implementation uses SHA-256 without salt.
   - Risk: Vulnerable to rainbow table attacks.
   - Mitigation: Implement bcrypt or Argon2 with proper salting and key stretching.

3. **4-Digit PIN Limitation**: 
   - Risk: Only 10,000 possible combinations, susceptible to brute force despite rate limiting.
   - Mitigation: Consider longer PINs or password-based authentication.

4. **Client-Side PIN Storage**:
   - Risk: Client-side JavaScript contains the PIN in plaintext.
   - Mitigation: Move all validation to server-side only.

## Testing Requirements

Each phase requires specific testing:

### Phase 1 Testing
- Verify admin page is accessible via "Admin utilities" link
- Confirm PIN entry works correctly (1446)
- Test Test/Normal toggle functionality in admin page
- Ensure toggle is no longer present in main dashboard

### Phase 2 Testing
- Verify PIN is no longer hardcoded
- Test rate limiting and account lockout functionality
- Ensure session management works correctly
- Test PIN reset functionality

### Phase 3 Testing
- Verify subscriber management UI works as expected
- Test data validation for subscriber information
- Confirm import/export functionality

## Completion Criteria

### Phase 1 Completion
- Admin page is accessible via "Admin utilities" link in About Us modal
- PIN protection is working with PIN=1446
- Test/Normal toggle is moved from dashboard.html to admin.html
- All functionality works correctly

### Future Phases Completion
- To be defined in detail as those phases begin
