// Password compatibility adapter: verifies supported Django password hashes inside Spring login.
// The private account snapshot carries hashes, not plaintext passwords; token issuance follows authentication.
// Changing password policy must remain compatible with Django account creation and the exporter.
package com.stockpilot.identity;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Base64;
import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;
import org.springframework.security.crypto.password.PasswordEncoder;

// Migration adapter: existing Django PBKDF2 passwords continue working without resets.
// Unsupported algorithms fail closed; password changes remain in Django for this release.
public final class DjangoPasswordEncoder implements PasswordEncoder {
    @Override public String encode(CharSequence raw) {
        // Spring generates a dummy hash for unknown-user timing protection.
        // No user password persistence endpoint is exposed by this adapter.
        byte[] random = new byte[18]; new SecureRandom().nextBytes(random);
        String salt = Base64.getUrlEncoder().withoutPadding().encodeToString(random);
        PBEKeySpec spec = new PBEKeySpec(raw.toString().toCharArray(),
            salt.getBytes(StandardCharsets.UTF_8), 1200000, 256);
        try {
            byte[] hash = SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256").generateSecret(spec).getEncoded();
            return "pbkdf2_sha256$1200000$" + salt + "$" + Base64.getEncoder().encodeToString(hash);
        } catch (Exception error) { throw new IllegalStateException("Password hashing unavailable", error); }
        finally { spec.clearPassword(); }
    }
    @Override public boolean matches(CharSequence raw, String encoded) {
        PBEKeySpec spec = null;
        try {
            String[] parts = encoded.split("\\$", -1);
            if (parts.length != 4 || !parts[0].equals("pbkdf2_sha256")) return false;
            int iterations = Integer.parseInt(parts[1]);
            if (iterations < 1 || iterations > 10000000) return false;
            byte[] expected = Base64.getDecoder().decode(parts[3]);
            if (expected.length != 32) return false;
            spec = new PBEKeySpec(raw.toString().toCharArray(),
                parts[2].getBytes(StandardCharsets.UTF_8), iterations, 256);
            byte[] actual = SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256").generateSecret(spec).getEncoded();
            return MessageDigest.isEqual(actual, expected);
        } catch (Exception invalid) { return false; }
        finally { if (spec != null) spec.clearPassword(); }
    }
}
