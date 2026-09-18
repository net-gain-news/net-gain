<?php
/**
 * Custom permalink structure for Seriously Simple Podcasting's `podcast` CPT.
 * Read directly from SSP's own source (class-cpt-podcast-handler.php) before
 * building this: its rewrite is a single flat slug, NOT nested under its own
 * `series` taxonomy. This filter + rule is what actually produces
 * /{show-slug}/{episode}/ rather than relying on something SSP doesn't do
 * natively.
 *
 * URL structure (revised 2026-09-18, see SPEC.md §6.2): each show lives at a
 * bare top-level slug - /edtech/, /edtech/{episode-slug}/ - not nested under
 * /shows/. The /shows/ path is reserved for the separate cross-show hub page
 * (SPEC.md §6.2's "all our shows" internal-linking page), which is an
 * ordinary WordPress Page, not something this class touches.
 *
 * The episode-matching pattern is restricted to registered show slugs
 * (queried from `ng_show`) rather than an unqualified `([^/]+)/([^/]+)/?$` -
 * a blanket two-segment wildcard would also swallow every show's own child
 * pages (episodes/index/subscribe/welcome, each a normal Page one level
 * under the show's page). The rule is additionally registered at 'bottom'
 * priority rather than 'top': WordPress's own auto-generated page rewrite
 * rules (which cover exactly those child pages) then get checked first, and
 * this rule only fires for a second segment that isn't an existing child
 * page - i.e. an actual episode post_name.
 *
 * Deploy note: adding/changing add_rewrite_rule() calls doesn't retroactively
 * update WordPress's cached compiled rewrite rules on an already-active
 * install - a flush (Settings -> Permalinks -> Save, or deactivate/reactivate
 * this plugin) is required once after deploying this file. Create/reparent
 * any show and child pages *before* that flush so their own page rules are
 * included in it.
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Net_Gain_Website_Rewrite {

	public static function register() {
		add_filter( 'post_type_link', array( __CLASS__, 'filter_permalink' ), 10, 2 );
		add_action( 'init', array( __CLASS__, 'add_rewrite_rules' ) );
	}

	public static function filter_permalink( $post_link, $post ) {
		if ( 'podcast' !== $post->post_type ) {
			return $post_link;
		}

		$terms = get_the_terms( $post->ID, 'series' );
		if ( empty( $terms ) || is_wp_error( $terms ) ) {
			return $post_link;
		}

		return home_url( "/{$terms[0]->slug}/{$post->post_name}/" );
	}

	public static function add_rewrite_rules() {
		$show_slugs = self::get_show_slugs();
		if ( empty( $show_slugs ) ) {
			return;
		}

		$pattern = '^(' . implode( '|', array_map( 'preg_quote', $show_slugs ) ) . ')/([^/]+)/?$';

		// Matched purely on the episode's own post_name (WordPress already enforces
		// post_name uniqueness within a post type) - the show-slug segment makes the
		// URL readable but isn't itself re-validated against the episode's series.
		add_rewrite_rule(
			$pattern,
			'index.php?post_type=podcast&name=$matches[2]',
			'bottom'
		);
	}

	/**
	 * Slugs of every registered show - these are the only first-path-segments
	 * this class's rewrite rule matches against.
	 */
	private static function get_show_slugs() {
		$show_ids = get_posts( array(
			'post_type'      => 'ng_show',
			'post_status'    => 'publish',
			'posts_per_page' => -1,
			'fields'         => 'ids',
		) );

		$slugs = array();
		foreach ( $show_ids as $show_id ) {
			$slug = get_post_field( 'post_name', $show_id );
			if ( $slug ) {
				$slugs[] = $slug;
			}
		}

		return $slugs;
	}
}
