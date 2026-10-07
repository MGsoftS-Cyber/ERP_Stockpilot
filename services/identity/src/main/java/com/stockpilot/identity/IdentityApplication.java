package com.stockpilot.identity;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

// Identity runs separately from the ERP: it authenticates users and issues access tokens.
// Express and Django validate those tokens; ERP domain services control stock and invoices.
@SpringBootApplication
public class IdentityApplication {
    public static void main(String[] args) {
        SpringApplication.run(IdentityApplication.class, args);
    }
}
