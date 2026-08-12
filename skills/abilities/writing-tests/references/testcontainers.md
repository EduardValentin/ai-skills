# Testcontainers Integration Setup

Read this only when the project runs its integration infrastructure with
Testcontainers.

The goal is real infrastructure for the application under test. Every dependency
is a Docker container the application talks to exactly as it would in
production, so nothing in the test path is mocked.

## Choosing The Pattern

Follow the project's existing Testcontainers pattern. Only when none exists,
consult the official Testcontainers documentation and pick the documented
pattern that fits the application structure.

## Representing Dependencies

- Model every third-party dependency as a container.
- Prefer the official Testcontainers module for that dependency. For a payment
  provider such as Stripe, check for an official module first.
- When no official module exists, still use a Testcontainers-compatible generic
  container that lets you configure an API — WireMock or MockServer. Configure
  the expectations there so the application calls it like any other third-party
  service.
- Use the appropriate official module from the Testcontainers documentation for
  the database.

## Structuring The Configuration

- Keep each container configuration in its own file. Never mix several
  dependencies into one configuration.
- Architect the configuration so more container-backed dependencies can be added
  later without touching the existing ones.
- Test scenarios inherit the container configuration they need. Never redeclare
  container setup per scenario — that duplicates instantiation.

## Wiring The Application To The Containers

- Testcontainers assigns dynamic ports. When the application reaches a
  dependency by URL and port, inject the mapped port during test setup.
- Never resolve a dynamic port inside a test scenario.
