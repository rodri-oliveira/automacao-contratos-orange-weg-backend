This is a [FastAPI](https://fastapi.tiangolo.com/) project bootstrapped with [Developers Portal](https://developers-portal.weg.net/).

## Getting Started

First, to run in development you may need to create a `.env` file in the root of the project.

This `.env` file should contain the given variables:

|Name|Description|Example|
|-|-|-|
|SWAGGER_SERVERS_LIST|List of servers divided by `,` that are passed to the [servers](https://swagger.io/docs/specification/api-host-and-base-path/) property of OpenAPI|`/,/api`|
|JWT_AUDIENCE|The [aud](https://datatracker.ietf.org/doc/html/rfc7519#section-4.1.3) claim value that will be asserted, usually the [client_id](https://www.oauth.com/oauth2-servers/client-registration/client-id-secret/) for the given application|`app_client_id`|
|JWT_ISSUER|The [iss](https://datatracker.ietf.org/doc/html/rfc7519#section-4.1.1) value that will be compared to the token claim |`https://auth-qa.weg.net`|


run the development server:

```bash
fastapi dev main.py
```

The API will be available at [http://localhost:3000/api](http://localhost:3000/api).

> You can find the docs at [http://localhost:3000/api](http://localhost:3000/api)

## Learn More

To leare more about FastAPI, take a look at the following resources:

- [FastAPI Documentation](https://fastapi.tiangolo.com/learn/) - learn about FastAPI features and API.