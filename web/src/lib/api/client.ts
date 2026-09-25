import createClient from "openapi-fetch";
import type { paths } from "./types.gen";

// Typed against the generated OpenAPI schema — never hand-write a response
// type (docs/05-API-SPEC.md section 10, docs/06 section 11).
// The real API mounts every route under /api/v1 itself (FastAPI bakes the
// prefix into each operation's path), so the generated `paths` keys already
// include it — baseUrl stays empty and every call below spells the full path.
export const api = createClient<paths>({
  baseUrl: "",
  credentials: "include",
});
