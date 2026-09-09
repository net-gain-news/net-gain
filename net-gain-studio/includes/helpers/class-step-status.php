<?php
/**
 * Canonical pipeline step keys, status values, and prerequisite ordering.
 *
 * Shared by the Episode CPT (default meta value) and the steps REST route
 * (prerequisite validation) so the two can never drift apart.
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Net_Gain_Step_Status {

	// Order matches Spec Section 10's 8 dashboard columns.
	const STEPS = array(
		'script_generated',
		'script_reviewed',
		'audio_received',
		'metadata_generated',
		'images_rendered',
		'captivate_published',
		'website_published',
		'youtube_published',
	);

	// Maps to the 5 dashboard colors (Section 10) plus the distinct "queued" treatment.
	const STATUSES = array( 'pending', 'in_progress', 'queued', 'done', 'degraded', 'failed' );

	/**
	 * Each step's prerequisites. Steps 1-3 (script generated/reviewed, audio
	 * received) are a strict chain. metadata_generated and images_rendered are
	 * SIBLINGS - both depend only on audio_received, neither on the other -
	 * per an explicit build-time decision (Phase 4): metadata generation is
	 * deliberately deferred close to publish time to avoid wasted work on
	 * episodes later aborted, but image generation must remain independently
	 * triggerable at any time (Section 8.3), so it cannot be gated behind
	 * metadata. This supersedes Section 8.3's original illustrative example
	 * ("image generation before that day's metadata exists" should be
	 * disabled), which assumed the two were chained. The three publish steps
	 * each require BOTH metadata_generated and images_rendered (Section 9's
	 * literal list of shared upstream steps) and are otherwise mutually
	 * independent - a failure in one must never block the other two.
	 */
	const PREREQUISITES = array(
		'script_generated'     => array(),
		'script_reviewed'      => array( 'script_generated' ),
		'audio_received'       => array( 'script_reviewed' ),
		'metadata_generated'   => array( 'audio_received' ),
		'images_rendered'      => array( 'audio_received' ),
		'captivate_published'  => array( 'metadata_generated', 'images_rendered' ),
		'website_published'    => array( 'metadata_generated', 'images_rendered' ),
		'youtube_published'    => array( 'metadata_generated', 'images_rendered' ),
	);

	public static function is_valid_step( $step_key ) {
		return in_array( $step_key, self::STEPS, true );
	}

	public static function is_valid_status( $status ) {
		return in_array( $status, self::STATUSES, true );
	}

	public static function default_status() {
		$status = array();
		foreach ( self::STEPS as $step ) {
			$status[ $step ] = array(
				'status' => 'pending',
				'at'     => null,
				'note'   => '',
			);
		}
		return $status;
	}

	/**
	 * Returns the first unmet prerequisite step key, or null if all are done.
	 *
	 * @param string $step_key    Step being attempted.
	 * @param array  $step_status Episode's current ng_step_status meta value.
	 */
	public static function unmet_prerequisite( $step_key, array $step_status ) {
		if ( ! isset( self::PREREQUISITES[ $step_key ] ) ) {
			return null;
		}
		foreach ( self::PREREQUISITES[ $step_key ] as $prereq ) {
			$current = isset( $step_status[ $prereq ]['status'] ) ? $step_status[ $prereq ]['status'] : 'pending';
			if ( 'done' !== $current && 'degraded' !== $current ) {
				return $prereq;
			}
		}
		return null;
	}

	/**
	 * Validates and applies one step transition against a full ng_step_status
	 * array, returning the updated array on success or a WP_Error on failure
	 * (invalid step/status, or an unmet prerequisite). Shared by the REST
	 * route (class-rest-episode-steps.php) and the admin UI's save handlers
	 * (Phase 4) so the two can never enforce this differently - the admin UI
	 * calls this directly rather than looping back through its own REST API.
	 */
	public static function apply_update( array $step_status, $step_key, $status, $note = '' ) {
		if ( ! self::is_valid_step( $step_key ) ) {
			return new WP_Error( 'ng_invalid_step', 'Unknown step: ' . $step_key, array( 'status' => 400 ) );
		}
		if ( ! self::is_valid_status( $status ) ) {
			return new WP_Error( 'ng_invalid_status', 'Unknown status: ' . $status, array( 'status' => 400 ) );
		}

		$blocker = self::unmet_prerequisite( $step_key, $step_status );
		if ( $blocker && 'pending' !== $status ) {
			return new WP_Error(
				'ng_prerequisite_not_met',
				"Cannot set {$step_key} to {$status}: prerequisite step \"{$blocker}\" is not done yet.",
				array( 'status' => 409 )
			);
		}

		$step_status[ $step_key ] = array(
			'status' => $status,
			'at'     => current_time( 'mysql' ),
			'note'   => $note,
		);

		return $step_status;
	}

	public static function rest_schema() {
		$properties = array();
		foreach ( self::STEPS as $step ) {
			$properties[ $step ] = array(
				'type'       => 'object',
				'properties' => array(
					'status' => array(
						'type' => 'string',
						'enum' => self::STATUSES,
					),
					'at'     => array(
						'type' => array( 'string', 'null' ),
					),
					'note'   => array(
						'type' => 'string',
					),
				),
			);
		}
		return array(
			'type'       => 'object',
			'properties' => $properties,
		);
	}
}
