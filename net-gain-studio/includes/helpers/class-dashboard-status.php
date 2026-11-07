<?php
/**
 * Derives a dashboard cell's displayed status and tooltip text (Spec
 * Section 10). "Queued" is computed here from data that already exists (ng_step_status + ng_finalization +
 * the show's publish_mode) rather than stored anywhere - nothing about
 * Phase 7 needed a new piece of persisted state.
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Net_Gain_Dashboard_Status {

	const PUBLISH_STEPS = array( 'captivate_published', 'website_published', 'youtube_published' );

	/**
	 * Returns one of: pending|in_progress|done|degraded|failed|queued.
	 */
	public static function compute_cell_status( $step_key, array $step_status, array $finalization, array $show ) {
		$stored = $step_status[ $step_key ]['status'] ?? 'pending';

		if (
			in_array( $step_key, self::PUBLISH_STEPS, true )
			&& 'pending' === $stored
			&& 'finalized' === ( $finalization['state'] ?? '' )
			&& 'scheduled' === ( $show['publish_mode'] ?? '' )
		) {
			return 'queued';
		}

		return $stored;
	}

	/** Plain-language status + specific troubleshooting guidance, seeded from this project's own real incidents - never generic "check the logs" text. */
	public static function tooltip( $step_key, $cell_status, array $step_status, array $show = array() ) {
		$note = $step_status[ $step_key ]['note'] ?? '';

		if ( 'youtube_published' === $step_key && 'pending' === $cell_status && empty( $show['youtube_connected'] ) ) {
			return 'This show has no YouTube channel connected - connect one on the show setup screen if this show should publish to YouTube. This will stay gray until then, not because anything is wrong.';
		}

		if ( 'kit_emailed' === $step_key && 'pending' === $cell_status && empty( $show['kit_enabled'] ) ) {
			return 'This show does not send its episode email through Kit (switch it on in the show setup screen). This stays gray until then, not because anything is wrong.';
		}

		if ( 'youtube_published' === $step_key && 'in_progress' === $cell_status ) {
			return 'Uploaded to YouTube - YouTube is still processing the video before it\'s genuinely live. This is an external delay outside our control (sometimes several minutes), not a failure; the next tick pass re-checks and resolves this to green or red.';
		}

		if ( 'queued' === $cell_status ) {
			return 'Finalized and ready - waiting for this show\'s configured scheduled publish time.';
		}

		if ( 'failed' === $cell_status ) {
			return self::failure_tooltip( $step_key, $note );
		}

		if ( 'degraded' === $cell_status ) {
			return self::degraded_tooltip( $step_key, $note );
		}

		if ( 'pending' === $cell_status ) {
			return 'Not reached yet.';
		}

		return '';
	}

	private static function failure_tooltip( $step_key, $note ) {
		$guidance = array(
			'script_generated'    => 'Script generation failed - check the tick loop log for the Claude API error, and confirm ANTHROPIC_API_KEY is set.',
			'metadata_generated'   => 'Metadata generation failed - check the tick loop log for the Claude API error.',
			'images_rendered'      => 'Image generation failed and no fallback image is available for this show yet - upload a default branded image in the show\'s setup screen.',
			'captivate_published'  => 'Captivate publish failed - check the logged raw response body first (SPEC Section 1: this API has previously returned undocumented error shapes that only the raw body reveals).',
			'website_published'    => 'Website publish failed - confirm Seriously Simple Podcasting is active and its "series" taxonomy exists, then check the tick loop log for the specific WordPress error.',
			'kit_emailed'          => 'The episode email was not sent through Kit - the logged note names the cause. A message about permissions or an unknown template or tag means the Kit settings on the show setup screen (or the API key) need fixing; a note that the episode is too old means Kit sending was down for over a day and the email was deliberately not sent late. Use Send email on the episode screen to try again; it never sends a second copy if Kit already has one.',
			'youtube_published'    => 'YouTube publishing failed - the logged note names the specific cause: a pre-publish checklist failure lists exactly which criteria (title/description/tags/thumbnail) didn\'t pass; a thumbnail-only failure almost always means the channel isn\'t phone-verified yet; "invalid_grant" means the OAuth connection was revoked or expired and the channel needs reconnecting on the show setup screen.',
		);
		$base = $guidance[ $step_key ] ?? 'This step failed - check the tick loop log for the specific error.';
		return $note ? "{$base} Logged note: {$note}" : $base;
	}

	private static function degraded_tooltip( $step_key, $note ) {
		$guidance = array(
			'script_generated' => 'The generated draft was suspiciously short for a real script - worth confirming it\'s not a truncated or non-script response (e.g. the model running out of its search budget) before reviewing. Not blocking.',
			'script_reviewed' => 'The saved final script was suspiciously close to the AI draft - worth a second look to confirm this wasn\'t an accidental save without real edits. Not blocking.',
			'images_rendered'  => 'AI image generation failed, so this show\'s pre-rendered default branded image was used instead - publishing was not blocked.',
			'youtube_published' => 'The video published successfully but its custom thumbnail could not be set - usually because the channel isn\'t phone-verified yet. The video is live with YouTube\'s own auto-generated thumbnail instead. Not blocking.',
		);
		$base = $guidance[ $step_key ] ?? 'Completed, but flagged for a second look. Not blocking.';
		return $note ? "{$base} ({$note})" : $base;
	}
}
