<?php
/**
 * GET /net-gain/v1/tick-context - the single call the Python tick loop makes
 * each pass (CLAUDE.md's architecture note). Returns every Active show with
 * its config, pending manual-trigger actions, today's effective talent, and
 * any in-flight episodes. Deciding *what's actually due* (schedules, queued
 * publish times) is the tick loop's own job (a later phase) - this endpoint
 * only reports state.
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Net_Gain_REST_Tick_Context {

	public function register_routes() {
		register_rest_route(
			'net-gain/v1',
			'/tick-context',
			array(
				'methods'             => 'GET',
				'callback'            => array( $this, 'get_context' ),
				'permission_callback' => function () {
					return current_user_can( 'edit_ng_shows' );
				},
			)
		);
	}

	public function get_context( WP_REST_Request $request ) {
		$today = current_time( 'Y-m-d' );

		$shows = get_posts(
			array(
				'post_type'      => Net_Gain_CPT_Show::POST_TYPE,
				'post_status'    => 'publish',
				'posts_per_page' => -1,
				'meta_key'       => 'ng_status',
				'meta_value'     => 'active',
			)
		);

		$result = array();
		foreach ( $shows as $show ) {
			$result[] = array(
				'id'                  => $show->ID,
				'name'                => $show->post_title,
				'slug'                => $show->post_name,
				'vertical_id'         => (int) get_post_meta( $show->ID, 'ng_vertical_id', true ),
				'recording_days'      => get_post_meta( $show->ID, 'ng_recording_days', true ),
				'target_time'         => get_post_meta( $show->ID, 'ng_target_time', true ),
				'recording_timezone'  => get_post_meta( $show->ID, 'ng_recording_timezone', true ),
				'lookback_days'       => (int) get_post_meta( $show->ID, 'ng_lookback_days', true ),
				'captivate_show_id'   => get_post_meta( $show->ID, 'ng_captivate_show_id', true ),
				'youtube_channel_id'  => get_post_meta( $show->ID, 'ng_youtube_channel_id', true ),
				'publish_mode'        => get_post_meta( $show->ID, 'ng_publish_mode', true ),
				'publish_time'        => get_post_meta( $show->ID, 'ng_publish_time', true ),
				'publish_timezone'    => get_post_meta( $show->ID, 'ng_publish_timezone', true ),
				'pending_actions'     => get_post_meta( $show->ID, 'ng_pending_actions', true ),
				'effective_talent_today' => Net_Gain_Talent_Assignments::get_effective_talent( $show->ID, $today ),
				'in_flight_episodes'  => $this->in_flight_episodes( $show->ID ),
			);
		}

		return rest_ensure_response( $result );
	}

	// Any episode where at least one of the 8 steps hasn't reached done/degraded/failed.
	private function in_flight_episodes( $show_id ) {
		$episodes = get_posts(
			array(
				'post_type'      => Net_Gain_CPT_Episode::POST_TYPE,
				'post_status'    => 'publish',
				'post_parent'    => $show_id,
				'posts_per_page' => 50,
				'orderby'        => 'date',
				'order'          => 'DESC',
			)
		);

		$in_flight = array();
		foreach ( $episodes as $episode ) {
			$step_status = get_post_meta( $episode->ID, 'ng_step_status', true );
			$settled     = array( 'done', 'degraded', 'failed' );
			$complete    = true;
			foreach ( Net_Gain_Step_Status::STEPS as $step ) {
				$status = isset( $step_status[ $step ]['status'] ) ? $step_status[ $step ]['status'] : 'pending';
				if ( ! in_array( $status, $settled, true ) ) {
					$complete = false;
					break;
				}
			}
			if ( $complete ) {
				continue;
			}

			$in_flight[] = array(
				'id'           => $episode->ID,
				'episode_date' => get_post_meta( $episode->ID, 'ng_episode_date', true ),
				'step_status'  => $step_status,
				'finalization' => get_post_meta( $episode->ID, 'ng_finalization', true ),
			);
		}

		return $in_flight;
	}
}
