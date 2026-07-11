/**
 * Safety requirement: the UI must clearly warn when BrowserTTSProvider
 * fallback mode is active for a generated clip (it does not clone voices).
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import GenerateVoicePage from "@/app/host/[sessionId]/generate/page";

jest.mock("next/navigation", () => ({
  useParams: () => ({ sessionId: "s1" }),
}));

// Defined inline inside the factory (rather than as an outer const) because
// jest.mock() factories run before any other module-scope statements due to
// hoisting, so referencing an outer `const` here would hit the temporal
// dead zone.
jest.mock("@/lib/api", () => ({
  api: {
    getSession: jest.fn().mockResolvedValue({
      id: "s1",
      retention_ttl_seconds: 86400,
      expires_at: new Date(Date.now() + 100000).toISOString(),
      ended_at: null,
      created_at: new Date().toISOString(),
      is_active: true,
      blocked_generation_count: 0,
      participants: [
        {
          id: "p1",
          display_name: "Alex",
          participant_token: "tok",
          consent_status: "granted",
          consent_timestamp: new Date().toISOString(),
          revoke_timestamp: null,
          has_audio_sample: true,
          audio_sample_expires_at: new Date(Date.now() + 100000).toISOString(),
        },
      ],
    }),
    generateVoice: jest.fn().mockResolvedValue({
      blocked: false,
      safety_label: "ok",
      blocked_reason: null,
      audio_url: "/generated-audio/abc",
      provider_used: "browser_tts_fallback",
      fallback_active: true,
      disclosure_text: "This is AI-generated audio...",
    }),
    audioUrl: (u: string) => `http://localhost:8000${u}`,
  },
}));

describe("Generate page fallback warning", () => {
  it("shows a fallback warning banner when BrowserTTSProvider was used", async () => {
    render(<GenerateVoicePage />);

    await screen.findByText(/Select a consenting participant/i);
    const textarea = screen.getByPlaceholderText(/Type a sentence/i);
    await userEvent.type(textarea, "Hello from the demo");

    const button = screen.getByText(/Run content filter and generate/i);
    await userEvent.click(button);

    await waitFor(() =>
      expect(screen.getByText(/Fallback mode active: BrowserTTSProvider was used/i)).toBeInTheDocument()
    );
    // Text spans multiple inline elements (a <strong>not</strong> in the
    // middle), so match against the rendered container text instead of a
    // single text node.
    expect(document.body.textContent).toMatch(/clone the participant.s voice/i);
  });
});
