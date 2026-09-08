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
	 * Each step's prerequisites. Steps 1-5 are a strict chain (Section 10's listed
	 * order, confirmed by Section 8.3's own example: "image generation before that
	 * day's metadata exists" should be disabled). Steps 6-8 (Captivate/website/
	 * YouTube publish) each depend only on images_rendered (which already implies
	 * the whole upstream chain) and are otherwise mutually independent per Section 9 -
	 * a failure in one must never block the other two.
	 */
	const PREREQUISITES = array(
		'script_generated'     => array(),
		'script_reviewed'      => array( 'script_generated' ),
		'audio_received'       => array( 'script_reviewed' ),
		'metadata_generated'   => array( 'audio_received' ),
		'images_rendered'      => array( 'metadata_generated' ),
		'captivate_published'  => array( 'images_rendered' ),
		'website_published'    => array( 'images_rendered' ),
		'youtube_published'    => array( 'images_rendered' ),
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
