/**
 * Safety requirement #13: no file input, drag-and-drop, or import path may
 * exist anywhere in the participant consent+recording flow. This test
 * renders the merged participant page in its recording-ready state and
 * asserts it never contains a file input or upload affordance.
 */
import { render, screen, waitFor } from "@testing-library/react";
import ParticipantPage from "@/app/participant/[participantToken]/page";

jest.mock("next/navigation", () => ({
  useParams: () => ({ participantToken: "tok-123" }),
}));

jest.mock("@/lib/api", () => ({
  api: {
    getParticipantByToken: jest.fn().mockResolvedValue({
      id: "p1",
      session_id: "s1",
      display_name: "Alex",
      consent_status: "granted",
      has_audio_sample: false,
      session_is_active: true,
    }),
    markConsentPhraseCaptured: jest.fn(),
    submitAudioSample: jest.fn(),
  },
  ApiError: class ApiError extends Error {},
}));

describe("Participant page has no upload/import affordance", () => {
  it("renders with no file input, drag-drop, or upload/import text", async () => {
    render(<ParticipantPage />);

    await waitFor(() => screen.getByText(/Start continuous recording/i));

    expect(document.querySelectorAll('input[type="file"]').length).toBe(0);
    expect(document.querySelectorAll('[draggable="true"]').length).toBe(0);

    const bodyText = document.body.textContent?.toLowerCase() || "";
    expect(bodyText).not.toMatch(/drag and drop/);
    expect(bodyText).not.toMatch(/choose a file/);
    expect(bodyText).not.toMatch(/paste a link/);
  });
});
