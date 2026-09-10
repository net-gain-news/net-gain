<?php
/**
 * admin_post handlers for the Show setup screen. Kept separate from the
 * Captivate connect action (Section 6.1's own "explicit connection action")
 * so the two forms on the edit screen post independently.
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Net_Gain_Admin_Actions {

	public static function register() {
		add_action( 'admin_post_ng_save_show', array( __CLASS__, 'save_show' ) );
		add_action( 'admin_post_ng_connect_captivate', array( __CLASS__, 'connect_captivate' ) );
		add_action( 'admin_post_ng_save_script_review', array( __CLASS__, 'save_script_review' ) );
		add_action( 'admin_post_ng_enqueue_action', array( __CLASS__, 'enqueue_action' ) );
	}

	public static function save_show() {
		if ( ! current_user_can( Net_Gain_Admin_Menu::CAPABILITY ) ) {
			wp_die( 'You do not have permission to do this.' );
		}
		check_admin_referer( 'ng_save_show', 'ng_save_show_nonce' );

		$show_id = isset( $_POST['show_id'] ) ? (int) $_POST['show_id'] : 0;
		$is_new  = 0 === $show_id;

		$postarr = array(
			'post_type'   => Net_Gain_CPT_Show::POST_TYPE,
			'post_status' => 'publish',
			'post_title'  => sanitize_text_field( wp_unslash( $_POST['ng_title'] ?? '' ) ),
			'post_name'   => sanitize_title( wp_unslash( $_POST['ng_slug'] ?? '' ) ),
		);

		if ( $is_new ) {
			$result  = wp_insert_post( $postarr, true );
			$show_id = is_wp_error( $result ) ? 0 : $result;
		} else {
			$postarr['ID'] = $show_id;
			$result        = wp_update_post( $postarr, true );
		}

		if ( is_wp_error( $result ) || ! $show_id ) {
			wp_die( 'Could not save show: ' . ( is_wp_error( $result ) ? esc_html( $result->get_error_message() ) : 'unknown error' ) );
		}

		self::save_meta( $show_id, $is_new );

		$primary_talent_id = isset( $_POST['ng_primary_talent'] ) ? (int) $_POST['ng_primary_talent'] : 0;
		if ( $primary_talent_id ) {
			Net_Gain_Talent_Assignments::set_primary( $show_id, $primary_talent_id );
		}

		if ( $is_new ) {
			$vertical_id = (int) get_post_meta( $show_id, 'ng_vertical_id', true );
			Net_Gain_Guidelines::seed_page_for_show( $show_id, $vertical_id );
		}

		wp_safe_redirect(
			add_query_arg(
				array(
					'page'      => Net_Gain_Admin_Menu::EDIT_SLUG,
					'show_id'   => $show_id,
					'ng_notice' => 'saved',
				),
				admin_url( 'admin.php' )
			)
		);
		exit;
	}

	private static function save_meta( $show_id, $is_new ) {
		// Vertical is set once at creation and never overwritten afterward (Section 4.1's
		// prospective-only-changes principle - the field is disabled in the UI on edit,
		// but we also refuse it server-side rather than trusting a hidden input alone).
		if ( $is_new ) {
			update_post_meta( $show_id, 'ng_vertical_id', (int) ( $_POST['ng_vertical_id'] ?? 0 ) );
		}

		update_post_meta( $show_id, 'ng_custom_domain', sanitize_text_field( wp_unslash( $_POST['ng_custom_domain'] ?? '' ) ) );

		$recording_days = isset( $_POST['ng_recording_days'] ) ? array_map( 'sanitize_key', wp_unslash( (array) $_POST['ng_recording_days'] ) ) : array();
		update_post_meta( $show_id, 'ng_recording_days', $recording_days );

		update_post_meta( $show_id, 'ng_target_time', sanitize_text_field( wp_unslash( $_POST['ng_target_time'] ?? '' ) ) );
		update_post_meta( $show_id, 'ng_recording_timezone', sanitize_text_field( wp_unslash( $_POST['ng_recording_timezone'] ?? '' ) ) );
		update_post_meta( $show_id, 'ng_lookback_days', max( 1, (int) ( $_POST['ng_lookback_days'] ?? 30 ) ) );

		$publish_mode = ( 'scheduled' === ( $_POST['ng_publish_mode'] ?? '' ) ) ? 'scheduled' : 'immediate';
		update_post_meta( $show_id, 'ng_publish_mode', $publish_mode );
		update_post_meta( $show_id, 'ng_publish_time', sanitize_text_field( wp_unslash( $_POST['ng_publish_time'] ?? '' ) ) );
		update_post_meta( $show_id, 'ng_publish_timezone', sanitize_text_field( wp_unslash( $_POST['ng_publish_timezone'] ?? '' ) ) );

		foreach ( array( 'ng_frame_square_id', 'ng_frame_16x9_id', 'ng_frame_1200x630_id' ) as $frame_key ) {
			update_post_meta( $show_id, $frame_key, (int) ( $_POST[ $frame_key ] ?? 0 ) );
		}

		foreach ( array( 'ng_fallback_square_id', 'ng_fallback_16x9_id', 'ng_fallback_1200x630_id' ) as $fallback_key ) {
			update_post_meta( $show_id, $fallback_key, (int) ( $_POST[ $fallback_key ] ?? 0 ) );
		}

		$image_style = ( 'duotone' === ( $_POST['ng_image_style'] ?? '' ) ) ? 'duotone' : 'none';
		update_post_meta( $show_id, 'ng_image_style', $image_style );
		update_post_meta( $show_id, 'ng_duotone_shadow_color', sanitize_hex_color( wp_unslash( $_POST['ng_duotone_shadow_color'] ?? '' ) ) ?: '' );
		update_post_meta( $show_id, 'ng_duotone_highlight_color', sanitize_hex_color( wp_unslash( $_POST['ng_duotone_highlight_color'] ?? '' ) ) ?: '' );

		$status = sanitize_key( $_POST['ng_status'] ?? 'active' );
		if ( ! in_array( $status, array( 'active', 'paused', 'concluded' ), true ) ) {
			$status = 'active';
		}
		update_post_meta( $show_id, 'ng_status', $status );

		update_post_meta( $show_id, 'ng_is_test', ! empty( $_POST['ng_is_test'] ) );
	}

	public static function connect_captivate() {
		if ( ! current_user_can( Net_Gain_Admin_Menu::CAPABILITY ) ) {
			wp_die( 'You do not have permission to do this.' );
		}
		check_admin_referer( 'ng_connect_captivate', 'ng_connect_captivate_nonce' );

		$show_id = isset( $_POST['show_id'] ) ? (int) $_POST['show_id'] : 0;
		if ( ! $show_id || Net_Gain_CPT_Show::POST_TYPE !== get_post_type( $show_id ) ) {
			wp_die( 'Show not found.' );
		}

		update_post_meta( $show_id, 'ng_captivate_show_id', sanitize_text_field( wp_unslash( $_POST['ng_captivate_show_id'] ?? '' ) ) );

		wp_safe_redirect(
			add_query_arg(
				array(
					'page'      => Net_Gain_Admin_Menu::EDIT_SLUG,
					'show_id'   => $show_id,
					'ng_notice' => 'captivate_connected',
				),
				admin_url( 'admin.php' )
			)
		);
		exit;
	}

	/**
	 * Similarity check (Spec Section 5.2): a suspiciously-close-to-identical
	 * final vs. draft is flagged (Amber/degraded), never blocked - a
	 * legitimate zero-edit day is possible.
	 */
	public static function save_script_review() {
		check_admin_referer( 'ng_save_script_review', 'ng_save_script_review_nonce' );

		$episode_id = isset( $_POST['episode_id'] ) ? (int) $_POST['episode_id'] : 0;
		if ( ! $episode_id || Net_Gain_CPT_Episode::POST_TYPE !== get_post_type( $episode_id ) ) {
			wp_die( 'Episode not found.' );
		}
		if ( ! Net_Gain_REST_Permissions::can_act_on_episode_finalization( $episode_id ) ) {
			wp_die( 'You do not have permission to review this episode.' );
		}

		$final = sanitize_textarea_field( wp_unslash( $_POST['script_final'] ?? '' ) );
		$draft = get_post_meta( $episode_id, 'ng_script_draft', true );

		similar_text( $draft, $final, $similarity_percent );
		$changed_percent = round( 100 - $similarity_percent );
		$is_suspicious    = $changed_percent < 8; // less than 8% changed - tunable.

		$status = $is_suspicious ? 'degraded' : 'done';
		$note   = "{$changed_percent}% changed from the AI draft";

		$step_status = get_post_meta( $episode_id, 'ng_step_status', true );
		$step_status = is_array( $step_status ) ? $step_status : Net_Gain_Step_Status::default_status();

		$result = Net_Gain_Step_Status::apply_update( $step_status, 'script_reviewed', $status, $note );
		if ( is_wp_error( $result ) ) {
			wp_die( esc_html( $result->get_error_message() ) );
		}

		update_post_meta( $episode_id, 'ng_script_final', $final );
		update_post_meta( $episode_id, 'ng_step_status', $result );

		wp_safe_redirect(
			add_query_arg(
				array(
					'page'       => Net_Gain_Script_Review_Page::SLUG,
					'episode_id' => $episode_id,
					'ng_notice'  => 'saved',
				),
				admin_url( 'admin.php' )
			)
		);
		exit;
	}

	/** Manual step triggers (Spec Section 8.3) - just enqueues; the tick loop does the work. */
	public static function enqueue_action() {
		if ( ! current_user_can( Net_Gain_Admin_Menu::CAPABILITY ) ) {
			wp_die( 'You do not have permission to do this.' );
		}
		check_admin_referer( 'ng_enqueue_action', 'ng_enqueue_action_nonce' );

		$show_id = isset( $_POST['show_id'] ) ? (int) $_POST['show_id'] : 0;
		$action  = sanitize_key( $_POST['episode_action'] ?? '' );

		if ( ! $show_id || ! in_array( $action, Net_Gain_REST_Show_Actions::ALLOWED_ACTIONS, true ) ) {
			wp_die( 'Invalid request.' );
		}

		$entry = array(
			'id'           => wp_generate_uuid4(),
			'action'       => $action,
			'episode_date' => sanitize_text_field( wp_unslash( $_POST['episode_date'] ?? current_time( 'Y-m-d' ) ) ),
			'requested_at' => current_time( 'mysql' ),
			'requested_by' => get_current_user_id(),
			'status'       => 'pending',
			'force'        => ! empty( $_POST['force'] ),
		);

		$pending   = get_post_meta( $show_id, 'ng_pending_actions', true );
		$pending   = is_array( $pending ) ? $pending : array();
		$pending[] = $entry;
		update_post_meta( $show_id, 'ng_pending_actions', $pending );

		$redirect = wp_get_referer() ?: admin_url( 'admin.php?page=' . Net_Gain_Admin_Menu::LIST_SLUG );
		wp_safe_redirect( add_query_arg( 'ng_notice', 'action_queued', $redirect ) );
		exit;
	}
}
