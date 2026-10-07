// Account bridge: loads the private identity snapshot exported from Django users and memberships.
// It preserves ERP identifiers and organization grants used when Spring creates access tokens.
// After trusted account changes, refresh the bootstrap snapshot and restart identity as documented.
package com.stockpilot.identity;

import java.nio.file.Path;
import java.util.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.security.core.userdetails.*;
import org.springframework.stereotype.Component;
import tools.jackson.databind.json.JsonMapper;

// A private, replaceable migration snapshot is the authoritative identity directory.
// Refresh the export and restart identity after role/password changes. Django also
// checks local membership, so stale identity grants cannot restore a revoked ERP role.
// Sessions/authorization codes are intentionally single-instance and restart-volatile.
@Component
public final class AccountDirectory implements UserDetailsService {
    public record Account(String id, String email, String password, Map<String, String> roles) {}
    private final Map<String, Account> emails = new HashMap<>();
    private final Map<String, Account> ids = new HashMap<>();
    public AccountDirectory(@Value("${stockpilot.accounts}") String filename) throws Exception {
        Account[] accounts = JsonMapper.builder().build().readValue(Path.of(filename).toFile(), Account[].class);
        for (Account a : accounts) {
            UUID.fromString(a.id());
            if (a.email() == null || a.password() == null || a.roles() == null)
                throw new IllegalArgumentException("Incomplete identity record");
            for (String organization : a.roles().keySet()) UUID.fromString(organization);
            if (emails.put(a.email().toLowerCase(Locale.ROOT), a) != null || ids.put(a.id(), a) != null)
                throw new IllegalArgumentException("Duplicate identity");
        }
    }
    @Override public UserDetails loadUserByUsername(String email) {
        Account a = emails.get(email.toLowerCase(Locale.ROOT));
        if (a == null) throw new UsernameNotFoundException("Invalid credentials");
        // UUID becomes the OIDC subject, not an email that can change later.
        return User.withUsername(a.id()).password(a.password()).roles("ERP_USER").build();
    }
    public Map<String, String> roles(String id) {
        Account a = ids.get(id);
        return a == null ? Map.of() : Map.copyOf(a.roles());
    }
}
