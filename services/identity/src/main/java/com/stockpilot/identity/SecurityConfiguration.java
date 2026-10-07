// Spring Security composition: configures OIDC authorization, sign-in and token issuance.
// React uses authorization code with PKCE; Express and Django verify issued access tokens.
// Identity authenticates accounts; it does not execute ERP stock or financial operations.
package com.stockpilot.identity;

import java.nio.file.*;
import java.nio.file.attribute.PosixFilePermissions;
import java.time.Duration;
import java.util.*;
import com.nimbusds.jose.jwk.*;
import com.nimbusds.jose.jwk.gen.RSAKeyGenerator;
import com.nimbusds.jose.jwk.source.*;
import com.nimbusds.jose.proc.SecurityContext;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.*;
import org.springframework.core.annotation.Order;
import org.springframework.http.MediaType;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.oauth2.core.*;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.server.authorization.OAuth2TokenType;
import org.springframework.security.oauth2.server.authorization.client.*;
import org.springframework.security.config.annotation.web.configuration.OAuth2AuthorizationServerConfiguration;
import org.springframework.security.oauth2.server.authorization.settings.*;
import org.springframework.security.oauth2.server.authorization.token.*;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.LoginUrlAuthenticationEntryPoint;
import org.springframework.security.web.util.matcher.MediaTypeRequestMatcher;
import org.springframework.web.cors.*;

@Configuration
public class SecurityConfiguration {
    @Bean @Order(1)
    SecurityFilterChain protocol(HttpSecurity http) throws Exception {
        http.oauth2AuthorizationServer(server -> {
            http.securityMatcher(server.getEndpointsMatcher());
            server.oidc(Customizer.withDefaults());
        });
        http.cors(Customizer.withDefaults()).authorizeHttpRequests(a -> a.anyRequest().authenticated())
            .exceptionHandling(e -> e.defaultAuthenticationEntryPointFor(
                new LoginUrlAuthenticationEntryPoint("/login"), new MediaTypeRequestMatcher(MediaType.TEXT_HTML)));
        return http.build();
    }
    @Bean @Order(2)
    SecurityFilterChain login(HttpSecurity http) throws Exception {
        // CSRF remains enabled on the Spring login and logout forms.
        http.cors(Customizer.withDefaults()).authorizeHttpRequests(a ->
            a.requestMatchers("/error").permitAll().anyRequest().authenticated())
            .formLogin(Customizer.withDefaults());
        return http.build();
    }
    @Bean PasswordEncoder passwordEncoder() { return new DjangoPasswordEncoder(); }
    @Bean RegisteredClientRepository clients(@Value("${stockpilot.web-origin}") String origin) {
        RegisteredClient web = RegisteredClient.withId("stockpilot-web")
            .clientId("stockpilot-web").clientAuthenticationMethod(ClientAuthenticationMethod.NONE)
            .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
            .redirectUri(origin + "/callback").postLogoutRedirectUri(origin + "/")
            .scope("openid").scope("profile").scope("erp")
            .clientSettings(ClientSettings.builder().requireProofKey(true).requireAuthorizationConsent(false).build())
            .tokenSettings(TokenSettings.builder().accessTokenTimeToLive(Duration.ofMinutes(5)).build()).build();
        // Public browser clients have no client secret and no password/refresh grants.
        return new InMemoryRegisteredClientRepository(web);
    }
    @Bean AuthorizationServerSettings serverSettings(@Value("${stockpilot.issuer}") String issuer) {
        return AuthorizationServerSettings.builder().issuer(issuer).build();
    }
    @Bean JWKSource<SecurityContext> keys(@Value("${stockpilot.signing-key}") String filename) throws Exception {
        Path file = Path.of(filename);
        Files.createDirectories(file.toAbsolutePath().getParent());
        if (!Files.exists(file)) {
            RSAKey key = new RSAKeyGenerator(3072).keyID(UUID.randomUUID().toString()).generate();
            // Persist keys across restarts; never generate a new key on every launch.
            Files.createFile(file, PosixFilePermissions.asFileAttribute(PosixFilePermissions.fromString("rw-------")));
            Files.writeString(file, key.toJSONString());
        }
        RSAKey key = RSAKey.parse(Files.readString(file));
        if (!key.isPrivate()) throw new IllegalStateException("Private signing key required");
        return new ImmutableJWKSet<>(new JWKSet(key));
    }
    @Bean JwtDecoder decoder(JWKSource<SecurityContext> source) {
        return OAuth2AuthorizationServerConfiguration.jwtDecoder(source);
    }
    @Bean OAuth2TokenCustomizer<JwtEncodingContext> claims(AccountDirectory accounts) {
        return context -> {
            if (OAuth2TokenType.ACCESS_TOKEN.equals(context.getTokenType())) {
                context.getClaims().audience(List.of("stockpilot-api"))
                    .claim("token_use", "access")
                    .claim("org_roles", accounts.roles(context.getPrincipal().getName()));
            }
        };
    }
    @Bean CorsConfigurationSource corsConfigurationSource(@Value("${stockpilot.web-origin}") String origin) {
        CorsConfiguration config = new CorsConfiguration();
        config.setAllowedOrigins(List.of(origin));
        config.setAllowedMethods(List.of("GET", "POST", "OPTIONS"));
        config.setAllowedHeaders(List.of("Content-Type", "Authorization"));
        config.setAllowCredentials(true);
        UrlBasedCorsConfigurationSource source = new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/**", config);
        return source;
    }
}
