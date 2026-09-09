<?php
/**
 * Custom permalink structure for Seriously Simple Podcasting's `podcast` CPT
 * (Spec Section 6.2: subdirectories are canonical). Read directly from SSP's
 * own source (class-cpt-podcast-handler.php) before building this: its
 * rewrite is a single flat slug, NOT nested under its own `series` taxonomy.
 * This filter + rule is what actually produces /shows/{show-slug}/{episode}/
 * rather than relying on something SSP doesn't do natively.
 *
 * Deploy note: adding a new add_rewrite_rule() call doesn't retroactively
 * update WordPress's cached compiled rewrite rules on an already-active
 * install - a flush (Settings -> Permalinks -> Save, or deactivate/reactivate
 * this plugin) is required once after deploying this file.
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

		return home_url( "/shows/{$terms[0]->slug}/{$post->post_name}/" );
	}

	public static function add_rewrite_rules() {
		// Matched purely on the episode's own post_name (WordPress already enforces
		// post_name uniqueness within a post type) - the show-slug segment makes the
		// URL readable but isn't itself re-validated against the episode's series.
		add_rewrite_rule(
			'^shows/([^/]+)/([^/]+)/?$',
			'index.php?post_type=podcast&name=$matches[2]',
			'top'
		);
	}
}
