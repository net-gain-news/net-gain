<?php
/**
 * Derives a dashboard cell's displayed status and tooltip text (Spec
 * Section 10). "Queued" and the audio-countdown's Blue state are computed
 * here from data that already exists (ng_step_status + ng_finalization +
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

		// The audio step reads "done" the instant it's uploaded, but isn't truly
		// settled until the countdown resolves (Section 10's own example of Blue).
		if ( 'audio_received' === $step_key && 'counting_down' === ( $finalization['state'] ?? '' ) ) {
			return 'in_progress';
		}

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
	public static function tooltip( $step_key, $cell_status, array $step_status ) {
		$note = $step_status[ $step_key ]['note'] ?? '';

		if ( 'youtube_published' === $step_key && 'pending' === $cell_status ) {
			return 'YouTube publishing is not built yet (Phase 9) - this will stay gray until then, not because anything is wrong.';
		}

		if ( 'queued' === $cell_status ) {
			return 'Finalized and ready - waiting for this show\'s configured scheduled publish time.';
		}

		if ( 'in_progress' === $cell_status && 'audio_received' === $step_key ) {
			return 'Audio received; finalizing automatically unless the talent aborts or publishes now from the My Show screen.';
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
			'youtube_published'    => 'YouTube publishing failed.',
		);
		$base = $guidance[ $step_key ] ?? 'This step failed - check the tick loop log for the specific error.';
		return $note ? "{$base} Logged note: {$note}" : $base;
	}

	private static function degraded_tooltip( $step_key, $note ) {
		$guidance = array(
			'script_generated' => 'The generated draft was suspiciously short for a real script - worth confirming it\'s not a truncated or non-script response (e.g. the model running out of its search budget) before reviewing. Not blocking.',
			'script_reviewed' => 'The saved final script was suspiciously close to the AI draft - worth a second look to confirm this wasn\'t an accidental save without real edits. Not blocking.',
			'images_rendered'  => 'AI image generation failed, so this show\'s pre-rendered default branded image was used instead - publishing was not blocked.',
		);
		$base = $guidance[ $step_key ] ?? 'Completed, but flagged for a second look. Not blocking.';
		return $note ? "{$base} ({$note})" : $base;
	}
}
