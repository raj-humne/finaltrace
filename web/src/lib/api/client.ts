import createClient from "openapi-fetch";
import type { paths } from "./types.gen";

// Typed against the generated OpenAPI schema — never hand-write a response
// type (docs/05-API-SPEC.md section 10, docs/06 section 11).
export const api = createClient<paths>({
  baseUrl: "/api/v1",
  credentials: "include",
});
