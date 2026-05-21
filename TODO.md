##Phase 1: The Codebase Core (Must be built before deployment)##

You must implement this now, because it changes the exact code you just wrote in api/client.ts and auth.py.

    [ ] 1. Implement HttpOnly Cookies for the JWT. * Why: If you deploy to the public internet with the token in localStorage, you ship a critical XSS vulnerability.

        Action: Refactor FastAPI to set the JWT in a Set-Cookie header. Refactor the React Axios client to use withCredentials: true and remove localStorage entirely.

Phase 2: The Containerization (The Bridge to Production)

This is the configuration required to safely move your code from your local machine to a cloud server (like Render, DigitalOcean, or an AWS EC2 instance).

    [ ] 2. Drop Docker Root Privileges.

        Why: If the container runs as root in the cloud, a breach of the container is a breach of the host server.

        Action: Add a RUN adduser and USER directive to your backend Dockerfile.

    [ ] 3. Strict Docker Networking.

        Why: In production, the database must be invisible to the internet.

        Action: Update docker-compose.yml to place FastAPI and React on a webnet, and FastAPI and PostgreSQL on an isolated dbnet.

Phase 3: The Production Gateway (Built during deployment)

These features are physically impossible to test accurately on localhost. They are native to the deployment environment.

    [ ] 4. SSL Termination & Reverse Proxy (HTTPS).

        Why: Secure HttpOnly cookies will be rejected by browsers in production unless the connection is encrypted via HTTPS.

        Action: Configure Nginx, Traefik, or your cloud provider's load balancer to handle the SSL certificate and route traffic to your FastAPI container.

    [ ] 5. API Rate Limiting.

        Why: To protect the expensive /upload parsing route from bringing down the server CPU.

        Action: Deploy a Redis container alongside FastAPI and implement the slowapi or fastapi-limiter library to cap requests.

Phase 4: The Kernel Lock (Post-Deployment Hardening)

Once the system is live and stable, you lock the lowest level of the data pipeline.

    [ ] 6. PostgreSQL Row-Level Security (RLS).

        Why: As you start testing with real financial data, you need mathematical proof that a routing bug cannot expose one user's ledger to another.

        Action: Write the SQL policies directly into the PostgreSQL database schema and modify the SQLAlchemy session to inject the current user's ID into the database context.
