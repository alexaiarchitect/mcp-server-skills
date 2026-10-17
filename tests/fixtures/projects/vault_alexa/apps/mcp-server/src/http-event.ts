/**
 * One request shape for both API Gateway payloads: REST API (v1, the hackathon
 * deployment, because only REST APIs can be X-Ray traced) and HTTP API (v2,
 * production). Pure functions, so tests and the local server use them too.
 */
import type {
  APIGatewayProxyEvent,
  APIGatewayProxyEventV2,
  APIGatewayProxyResult
} from "aws-lambda";

export type ApiEvent = APIGatewayProxyEvent | APIGatewayProxyEventV2;

export interface NormalizedRequest {
  method: string;
  path: string;
  query: URLSearchParams;
  headers: Record<string, string>;
  body: string;
  requestId: string;
  traceHeader?: string;
}

function isV2(event: ApiEvent): event is APIGatewayProxyEventV2 {
  return (event as APIGatewayProxyEventV2).version === "2.0";
}

export function normalizeEvent(event: ApiEvent): NormalizedRequest {
  const headers: Record<string, string> = {};
  for (const [key, value] of Object.entries(
    (event.headers as Record<string, string | undefined> | null) ?? {}
  )) {
    if (typeof value === "string") headers[key.toLowerCase()] = value;
  }
  const rawBody = event.body ?? "";
  const body = event.isBase64Encoded ? Buffer.from(rawBody, "base64").toString("utf8") : rawBody;
  if (isV2(event)) {
    return {
      method: event.requestContext.http.method.toUpperCase(),
      path: event.rawPath,
      query: new URLSearchParams(event.rawQueryString),
      headers,
      body,
      requestId: event.requestContext.requestId,
      ...(headers["x-amzn-trace-id"] ? { traceHeader: headers["x-amzn-trace-id"] } : {})
    };
  }
  const query = new URLSearchParams();
  for (const [key, values] of Object.entries(event.multiValueQueryStringParameters ?? {})) {
    for (const value of values ?? []) query.append(key, value);
  }
  if (![...query.keys()].length) {
    for (const [key, value] of Object.entries(event.queryStringParameters ?? {})) {
      if (value !== undefined) query.set(key, value);
    }
  }
  return {
    method: event.httpMethod.toUpperCase(),
    // REST APIs on a custom domain with a base-path mapping of "(none)" put
    // the resource path in `path`; strip a stage prefix if one leaked in.
    path: event.path.replace(/^\/(prod|hackathon)(?=\/)/u, ""),
    query,
    headers,
    body,
    requestId: event.requestContext.requestId,
    ...(headers["x-amzn-trace-id"] ? { traceHeader: headers["x-amzn-trace-id"] } : {})
  };
}

export function respond(
  statusCode: number,
  body: string,
  headers: Record<string, string> = {}
): APIGatewayProxyResult {
  return { statusCode, headers, body, isBase64Encoded: false };
}

export function json(
  statusCode: number,
  value: unknown,
  headers: Record<string, string> = {}
): APIGatewayProxyResult {
  return respond(statusCode, JSON.stringify(value), {
    "content-type": "application/json",
    "cache-control": "no-store",
    ...headers
  });
}

/** Convert a fetch Response (fully buffered; Lambda proxy integrations cannot stream) to a proxy result. */
export async function fromResponse(response: Response): Promise<APIGatewayProxyResult> {
  const headers: Record<string, string> = {};
  response.headers.forEach((value, key) => {
    headers[key] = value;
  });
  return respond(response.status, await response.text(), headers);
}
