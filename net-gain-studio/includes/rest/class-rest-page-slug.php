<?php
/**
 * POST /net-gain/v1/episodes/{id}/page-slug - renames a just-published episode page's address and leaves NO trace of
 * the old one. WordPress normally remembers a changed slug (_wp_old_slug) and redirects from it, which is right for a
 * page search engines may know but is clutter for one republished within hours of going live because its headline
 * was rewritten. This route therefore refuses any page older than FRESH_HOURS: an aged page keeps WordPress's own
 * redirect behaviour and has to be renamed by hand.
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Net_Gain_REST_Page_Slug {

	const FRESH_HOURS = 48;

	public function register_routes() {
		register_rest_route(
			'net-gain/v1',
			'/episodes/(?P<id>\d+)/page-slug',
			array(
				'methods'             => 'POST',
				'callback'            => array( $this, 'rename' ),
				'permission_callback' => function ( WP_REST_Request $request ) {
					return Net_Gain_REST_Permissions::can_manage_episode( (int) $request['id'] );
				},
			)
		);
	}

	/** Pure: true when a page published at $published_gmt (Y-m-d H:i:s, GMT) is still inside the window at $now (unix). */
	public static function is_fresh( $published_gmt, $now ) {
		$published = strtotime( $published_gmt . ' UTC' );
		return false !== $published && ( $now - $published ) <= self::FRESH_HOURS * HOUR_IN_SECONDS;
	}

	public function rename( WP_REST_Request $request ) {
		$episode_id = (int) $request['id'];
		$post_id    = (int) get_post_meta( $episode_id, 'ng_website_post_id', true );
		$post       = $post_id ? get_post( $post_id ) : null;
		if ( ! $post || 'podcast' !== $post->post_type ) {
			return new WP_Error( 'ng_page_not_found', 'This episode has no public page yet.', array( 'status' => 404 ) );
		}

		$slug = sanitize_title( (string) $request->get_param( 'slug' ) );
		if ( '' === $slug ) {
			return new WP_Error( 'ng_bad_request', 'A slug is required.', array( 'status' => 400 ) );
		}
		if ( ! self::is_fresh( $post->post_date_gmt, time() ) ) {
			return new WP_Error( 'ng_page_too_old', 'This page is older than ' . self::FRESH_HOURS . ' hours; rename it by hand so WordPress keeps the redirect.', array( 'status' => 409 ) );
		}

		if ( $slug !== $post->post_name ) {
			$result = wp_update_post( array( 'ID' => $post_id, 'post_name' => $slug ), true );
			if ( is_wp_error( $result ) ) {
				return new WP_Error( 'ng_rename_failed', $result->get_error_message(), array( 'status' => 500 ) );
			}
		}
		delete_post_meta( $post_id, '_wp_old_slug' );

		$permalink = get_permalink( $post_id );
		update_post_meta( $episode_id, 'ng_url_website', $permalink );
		return rest_ensure_response( array( 'post_id' => $post_id, 'permalink' => $permalink ) );
	}
}
