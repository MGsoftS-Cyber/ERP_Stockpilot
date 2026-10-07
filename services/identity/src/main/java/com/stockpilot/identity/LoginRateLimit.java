package com.stockpilot.identity;

import java.io.IOException;
import java.util.HashMap;
import java.util.Map;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.*;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

// The sign-in server is directly browser-accessible, so it applies its own request limiter.
// Gateway limits alone cannot protect requests sent directly to the identity service.
// Single-instance bounded memory. Do not trust arbitrary X-Forwarded-For headers.
@Component @Order(-200)
public class LoginRateLimit extends OncePerRequestFilter {
    private record Bucket(long start, int attempts) {}
    private final Map<String, Bucket> buckets = new HashMap<>();
    private synchronized boolean allowed(String address) {
        long now = System.currentTimeMillis();
        buckets.entrySet().removeIf(e -> now - e.getValue().start() > 60000);
        Bucket b = buckets.getOrDefault(address, new Bucket(now, 0));
        if (b.attempts() >= 20 || (!buckets.containsKey(address) && buckets.size() >= 10000)) return false;
        buckets.put(address, new Bucket(b.start(), b.attempts() + 1));
        return true;
    }
    @Override protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response,
                                              FilterChain chain) throws ServletException, IOException {
        if (request.getMethod().equals("POST") &&
            (request.getRequestURI().equals("/login") || request.getRequestURI().equals("/oauth2/token")) &&
            !allowed(request.getRemoteAddr())) {
            response.setStatus(429); response.setHeader("Retry-After", "60");
            response.setContentType("application/json");
            response.getWriter().write("{\"error\":\"rate_limited\"}"); return;
        }
        chain.doFilter(request, response);
    }
}
