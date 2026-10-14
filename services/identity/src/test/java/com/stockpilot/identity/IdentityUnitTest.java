package com.stockpilot.identity;

import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.Base64;
import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import static org.junit.jupiter.api.Assertions.*;

class IdentityUnitTest {
    @TempDir Path temporary;
    @Test void compatiblePasswordsAndMalformedHashes() throws Exception {
        var encoder = new DjangoPasswordEncoder();
        byte[] hash = SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256")
            .generateSecret(new PBEKeySpec("test-password".toCharArray(), "salt".getBytes(StandardCharsets.UTF_8), 1000, 256)).getEncoded();
        String encoded = "pbkdf2_sha256$1000$salt$" + Base64.getEncoder().encodeToString(hash);
        assertTrue(encoder.matches("test-password", encoded));
        assertFalse(encoder.matches("wrong", encoded));
        assertFalse(encoder.matches("test-password", "invalid"));
        assertFalse(encoder.matches("test-password", "pbkdf2_sha256$-1$salt$bad"));
        assertTrue(encoder.matches("secret", encoder.encode("secret")));
    }
    @Test void subjectsStayUuidAndGrantsStayTenantScoped() throws Exception {
        Path file = temporary.resolve("accounts.json");
        String id = "11111111-1111-1111-1111-111111111111";
        String org = "22222222-2222-2222-2222-222222222222";
        Files.writeString(file, "[{\"id\":\"" + id + "\",\"email\":\"user@test.local\",\"password\":\"hash\",\"roles\":{\"" + org + "\":\"VIEWER\"}}]");
        var directory = new AccountDirectory(file.toString());
        assertEquals(id, directory.loadUserByUsername("USER@test.local").getUsername());
        assertEquals("VIEWER", directory.roles(id).get(org));
        assertTrue(directory.roles("unknown").isEmpty());
    }
    @Test void keysSurviveRestart() throws Exception {
        Path key = temporary.resolve("signing.jwk");
        var config = new SecurityConfiguration();
        config.keys(key.toString());
        String first = Files.readString(key);
        config.keys(key.toString());
        assertEquals(first, Files.readString(key));
    }
}
