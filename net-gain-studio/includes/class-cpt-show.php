<?php
/**
 * Show: one underwriter's live deployment of a Vertical (Spec Section 4).
 * post_name (the CPT's own slug) doubles as the website subdirectory slug -
 * no separate meta key, gets WP's native uniqueness/sanitization for free.
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Net_Gain_CPT_Show {

	const POST_TYPE = 'ng_show';

	public static function register() {
		register_post_type(
			self::POST_TYPE,
			array(
				'label'           => 'Shows',
				'public'          => false,
				'show_ui'         => false,
				'show_in_menu'    => false,
				'show_in_rest'    => true,
				'rest_base'       => self::POST_TYPE,
				// 'custom-fields' is required for WP_REST_Posts_Controller to expose
				// or accept the 'meta' field at all - without it, register_post_meta's
				// show_in_rest schema is registered but never wired into the actual
				// REST request/response handling, so every meta read/write via the
				// generic wp/v2/ng_show route silently no-ops. No UI side effect here:
				// show_ui is false, so there's no post-edit screen for a Custom Fields
				// metabox to appear on.
				'supports'        => array( 'title', 'custom-fields' ),
				'capability_type' => array( 'ng_show', 'ng_shows' ),
				'map_meta_cap'    => true,
				'hierarchical'    => false,
			)
		);

		self::register_meta();

		add_action( 'rest_api_init', array( __CLASS__, 'register_rest_fields' ) );
	}

	/**
	 * ng_guidelines_html (2026-09-25): the guidelines page's content, resolved
	 * server-side and attached directly to the Show's own REST response,
	 * rather than making the pipeline fetch the page itself via
	 * /wp/v2/pages/{id}. That generic core route enforces a real permission
	 * check on non-'publish'-status content (read_private_pages) - which is
	 * exactly what broke script generation the day the guidelines page moved
	 * to post_status=private (2026-09-24): the pipeline's Application-
	 * Password account doesn't clear that check, unlike everything else it
	 * touches, which is either 'publish'-status or a custom net-gain/v1
	 * route with its own permission callback. get_post_field() here runs
	 * unrestricted PHP-side, so this sidesteps that capability question
	 * entirely instead of trying to grant the account a capability.
	 */
	public static function register_rest_fields() {
		register_rest_field(
			self::POST_TYPE,
			'ng_guidelines_html',
			array(
				'get_callback' => function ( $object ) {
					$page_id = (int) get_post_meta( $object['id'], 'ng_guidelines_page_id', true );
					return $page_id ? (string) get_post_field( 'post_content', $page_id ) : '';
				},
				'schema'       => array(
					'type'        => 'string',
					'description' => "This show's editorial guidelines, resolved server-side regardless of the guidelines page's own REST visibility.",
					'context'     => array( 'view', 'edit' ),
				),
			)
		);
	}

	/** Canonical list of Show meta keys - reused by the Phase 2 admin save handler so the two can never drift apart. */
	public static function meta_keys() {
		return array_keys( self::field_definitions() );
	}

	private static function register_meta() {
		$auth_callback = function ( $allowed, $meta_key, $post_id ) {
			return current_user_can( 'edit_post', $post_id );
		};

		foreach ( self::field_definitions() as $key => $args ) {
			register_post_meta(
				self::POST_TYPE,
				$key,
				array_merge(
					array(
						'single'        => true,
						'show_in_rest'  => true,
						'auth_callback' => $auth_callback,
					),
					$args
				)
			);
		}
	}

	private static function field_definitions() {
		return array(
			'ng_vertical_id'         => array( 'type' => 'integer', 'default' => 0 ),
			'ng_custom_domain'       => array( 'type' => 'string', 'default' => '' ),
			'ng_recording_days'      => array(
				'type'       => 'array',
				'default'    => array(),
				'show_in_rest' => array(
					'schema' => array(
						'type'  => 'array',
						'items' => array( 'type' => 'string', 'enum' => array( 'mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun' ) ),
					),
				),
			),
			'ng_target_time'         => array( 'type' => 'string', 'default' => '' ),
			'ng_recording_timezone'  => array( 'type' => 'string', 'default' => '' ),
			'ng_lookback_days'       => array( 'type' => 'integer', 'default' => 30 ),
			'ng_guidelines_page_id'  => array( 'type' => 'integer', 'default' => 0 ),
			'ng_frame_square_id'     => array( 'type' => 'integer', 'default' => 0 ),
			'ng_frame_16x9_id'       => array( 'type' => 'integer', 'default' => 0 ),
			'ng_frame_1200x630_id'   => array( 'type' => 'integer', 'default' => 0 ),
			// Pre-rendered, finished images (already run through all three frames/formats) -
			// used automatically if AI image generation fails (Spec Section 7's required
			// graceful fallback). Not re-composited at fallback time, just copied as-is.
			'ng_fallback_square_id'    => array( 'type' => 'integer', 'default' => 0 ),
			'ng_fallback_16x9_id'      => array( 'type' => 'integer', 'default' => 0 ),
			'ng_fallback_1200x630_id'  => array( 'type' => 'integer', 'default' => 0 ),
			// Optional per-show duotone treatment (Spec Section 7) - applied to the AI base
			// image before per-format cropping/frame compositing. Only the two colors vary
			// per show; the blend algorithm itself (contrast/brightness/opacities) is fixed
			// in pipeline/image_compositing.py, not configurable here.
			'ng_image_style'             => array( 'type' => 'string', 'default' => 'none' ), // none|duotone
			'ng_duotone_shadow_color'    => array( 'type' => 'string', 'default' => '' ),
			'ng_duotone_highlight_color' => array( 'type' => 'string', 'default' => '' ),
			'ng_status'              => array( 'type' => 'string', 'default' => 'active' ), // active|paused|concluded - never "archived", see Spec 4.2.
			'ng_is_test'             => array( 'type' => 'boolean', 'default' => false ), // Spec Section 13 - hidden from the dashboard by default.
			'ng_captivate_show_id'   => array( 'type' => 'string', 'default' => '' ),
			'ng_youtube_channel_id'  => array( 'type' => 'string', 'default' => '' ), // non-secret; OAuth tokens live in wp_ng_secrets.
			'ng_youtube_channel_title'   => array( 'type' => 'string', 'default' => '' ), // non-secret; captured at connect time.
			// Proxy for YouTube's phone-verification requirement (Spec Section 6.3) -
			// captured once at connect time from channels.list's status.longUploadsStatus,
			// not a documented verification field directly. 'disallowed' == not verified.
			'ng_youtube_phone_verified'  => array( 'type' => 'string', 'default' => '' ),
			'ng_publish_mode'        => array( 'type' => 'string', 'default' => 'immediate' ), // immediate|scheduled
			'ng_publish_time'        => array( 'type' => 'string', 'default' => '' ),
			'ng_publish_timezone'    => array( 'type' => 'string', 'default' => '' ),
			// Edtech Index (Google Sheet sync, 2026-09-21) - empty string means
			// this show has no index page. Accepts the sheet's full editor URL
			// (…/edit?gid=0#gid=0, whatever a human copies from the address bar)
			// or a bare sheet id; pipeline/edtech_index.py parses either.
			'ng_index_sheet_url'          => array( 'type' => 'string', 'default' => '' ),
			// Written only by POST /shows/{id}/index-snapshot (tick.py) - never
			// hand-edited. Whole-snapshot replace on every successful fetch, so
			// constituents can be added/removed in the sheet at any time with no
			// corresponding change needed here.
			'ng_index_snapshot'           => array(
				'type'         => 'object',
				'default'      => array(),
				'show_in_rest' => array(
					'schema' => array(
						'type'       => 'object',
						'properties' => array(
							'as_of'                => array( 'type' => 'string' ),
							'total_index_value'    => array( 'type' => array( 'number', 'null' ) ),
							'daily_change_dollar'  => array( 'type' => array( 'number', 'null' ) ),
							'daily_change_percent' => array( 'type' => array( 'number', 'null' ) ),
							'ytd_change_percent'   => array( 'type' => array( 'number', 'null' ) ),
							'constituent_count'    => array( 'type' => 'integer' ),
							'constituents'         => array(
								'type'  => 'array',
								'items' => array(
									'type'       => 'object',
									'properties' => array(
										'ticker'             => array( 'type' => 'string' ),
										'exchange'           => array( 'type' => 'string' ),
										'company'            => array( 'type' => 'string' ),
										'country'            => array( 'type' => 'string' ),
										'segment'            => array( 'type' => 'string' ),
										'price'              => array( 'type' => array( 'number', 'null' ) ),
										'day_change_percent' => array( 'type' => array( 'number', 'null' ) ),
										'position_value'     => array( 'type' => array( 'number', 'null' ) ),
										'ytd_change_percent' => array( 'type' => array( 'number', 'null' ) ),
									),
								),
							),
						),
					),
				),
			),
			// Site-local Y-m-d of the last successful refresh - the "once per
			// business day" guard tick.py itself checks against (in NY time, not
			// this site-local date); stored here only so a human glancing at the
			// record can tell when it last actually succeeded.
			'ng_index_last_refresh_date'  => array( 'type' => 'string', 'default' => '' ),
			// Independent of the date above so a *failed* attempt is visible even
			// on a day a prior success already set the date - surfaced on the ops
			// dashboard (Section 10) so a silently-broken sheet (e.g. sharing
			// tightened) gets noticed instead of the site quietly going stale.
			'ng_index_last_refresh_status' => array(
				'type'         => 'object',
				'default'      => array(),
				'show_in_rest' => array(
					'schema' => array(
						'type'       => 'object',
						'properties' => array(
							'status'  => array( 'type' => 'string' ), // success|failed
							'at'      => array( 'type' => 'string' ),
							'message' => array( 'type' => 'string' ),
						),
					),
				),
			),
			'ng_pending_actions'     => array(
				'type'    => 'array',
				'default' => array(),
				'show_in_rest' => array(
					'schema' => array(
						'type'  => 'array',
						'items' => array(
							'type'       => 'object',
							'properties' => array(
								'id'           => array( 'type' => 'string' ),
								'action'       => array( 'type' => 'string' ),
								'episode_date' => array( 'type' => 'string' ),
								'requested_at' => array( 'type' => 'string' ),
								'requested_by' => array( 'type' => 'integer' ),
								'status'       => array( 'type' => 'string' ),
								'force'        => array( 'type' => 'boolean' ),
							),
						),
					),
				),
			),
		);
	}
}
