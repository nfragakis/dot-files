import type { ExtensionAPI } from "@oh-my-pi/pi-coding-agent";

export default function (pi: ExtensionAPI) {
	pi.on("session_start", (_event, ctx) => {
		if (!ctx.hasUI || process.env.TERM_PROGRAM !== "tern") return;
		// omp 18.8.6 adopts an already-started composer before installing its
		// enhanced-paste start listener. Enable it once the live session is ready.
		// omp's existing OSC 5522 handler owns MIME negotiation and attachments.
		process.stdout.write("\x1b[?5522h");
	});
}
