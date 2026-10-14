FROM maven:3.9-eclipse-temurin-21 AS build
WORKDIR /src
COPY pom.xml .
COPY src ./src
RUN mvn -B verify
FROM eclipse-temurin:21-jre-alpine
WORKDIR /app
RUN addgroup -g 10001 identity && adduser -D -u 10001 -G identity identity && mkdir /data && chown identity:identity /data
COPY --from=build /src/target/identity-0.11.0.jar /app/identity.jar
USER identity
EXPOSE 9000
ENTRYPOINT ["java", "-jar", "/app/identity.jar"]
