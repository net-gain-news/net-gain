<?php
/**
 * Prevents permanently deleting a WordPress media attachment that an
 * Episode or Show still references (audio, images, branding frames,
 * fallback images).
 *
 * Built 2026-09-30 after a real incident: an Episode's master audio file
 * was permanently deleted directly from the Media Library - nothing in
 * this plugin ever asked whether anything still pointed at it, so the
 * episode's own ng_audio_attachment_id meta silently went stale, and the
 * break only surfaced days later, as a YouTube publish failure. Root cause
 * wasn't carelessness - the Media Library gives no indication a given file
 * is load-bearing for a specific episode, and this plugin creates four new
 * attachments (audio + 3 images) per episode per day, so that list grows
 * fast and starts looking like safe-to-clean-up clutter.
 *
 * Two independent layers, deliberately not just one:
 * - map_meta_cap on 'delete_post' covers the normal paths (wp-admin UI,
 *   the REST API) by making the delete capability itself unavailable -
 *   WordPress's own UI then simply hides the delete option, no custom
 *   error needed.
 * - delete_attachment is a second, code-path-independent net: core's own
 *   wp_delete_post() performs no capability check internally (callers are
 *   expected to check first), so anything that calls it directly - WP-CLI's
 *   own `wp post delete`, or any other direct PHP call - would skip the
 *   first layer entirely. This one hard wp_die()s instead, which is blunt
 *   but halts execution before either the DB row or the file on disk is
 *   removed, regardless of how deletion was invoked.
 *
 *   Confirmed live (2026-09-30) that `before_delete_post` is the wrong hook
 *   for this: wp_delete_post() takes a completely separate internal branch
 *   for post_type=attachment that never fires before_delete_post/
 *   after_delete_post at all - only delete_attachment. An earlier version
 *   of this file used before_delete_post and, tested directly against a
 *   disposable attachment, did not block a real WP-CLI `--force` delete -
 *   caught immediately by testing on a throwaway file, not on anything
 *   real, but worth the explicit note given how easy it would be to
 *   silently ship a guard that only protects half its own two layers.
 *
 * Deliberately does NOT protect items only moved to Trash (wp_trash_post())
 * - that's already reversible, no need to block it. Only permanent deletion
 * (from Trash, or a force-delete) is guarded.
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Net_Gain_Attachment_Guard {

	const EPISODE_ATTACHMENT_KEYS = array(
		'ng_audio_attachment_id',
		'ng_image_square_id',
		'ng_image_16x9_id',
		'ng_image_1200x630_id',
	);

	const SHOW_ATTACHMENT_KEYS = array(
		'ng_frame_square_id',
		'ng_frame_16x9_id',
		'ng_frame_1200x630_id',
		'ng_fallback_square_id',
		'ng_fallback_16x9_id',
		'ng_fallback_1200x630_id',
	);

	// Per-request cache - find_usage() is called from both the capability
	// filter (fires per-row on the Media Library list) and the column
	// renderer (fires again per-row for the same list) - without this, a
	// 20-item Media Library page would run the lookup twice per item.
	private static $cache = array();

	public static function register() {
		add_filter( 'map_meta_cap', array( __CLASS__, 'block_delete_of_in_use_attachment' ), 10, 4 );
		add_action( 'delete_attachment', array( __CLASS__, 'block_universal_delete' ) );
		add_filter( 'manage_media_columns', array( __CLASS__, 'add_used_by_column' ) );
		add_action( 'manage_media_custom_column', array( __CLASS__, 'render_used_by_column' ), 10, 2 );
	}

	public static function block_delete_of_in_use_attachment( $caps, $cap, $user_id, $args ) {
		if ( 'delete_post' !== $cap || empty( $args[0] ) ) {
			return $caps;
		}
		$post_id = (int) $args[0];
		if ( 'attachment' !== get_post_type( $post_id ) ) {
			return $caps;
		}
		if ( self::find_usage( $post_id ) ) {
			$caps[] = 'do_not_allow';
		}
		return $caps;
	}

	public static function block_universal_delete( $post_id ) {
		if ( 'attachment' !== get_post_type( $post_id ) ) {
			return;
		}
		$used_by = self::find_usage( $post_id );
		if ( ! $used_by ) {
			return;
		}
		wp_die(
			esc_html(
				"This file is still in use by {$used_by['label']} and can't be permanently deleted. " .
				'Edit that record and clear or replace the reference there first, then this file can be deleted.'
			),
			'Net Gain Studio: file still in use',
			array( 'response' => 403, 'back_link' => true )
		);
	}

	public static function add_used_by_column( $columns ) {
		$columns['ng_used_by'] = 'Used By (Net Gain Studio)';
		return $columns;
	}

	public static function render_used_by_column( $column_name, $attachment_id ) {
		if ( 'ng_used_by' !== $column_name ) {
			return;
		}
		$used_by = self::find_usage( $attachment_id );
		if ( ! $used_by ) {
			echo '&#8212;';
			return;
		}
		printf(
			'<a href="%s">%s</a>',
			esc_url( get_edit_post_link( $used_by['post_id'] ) ),
			esc_html( $used_by['label'] )
		);
	}

	/**
	 * Returns array('post_id' => ..., 'label' => ...) for the first Episode
	 * or Show that references this attachment, or null if none do. One
	 * direct, indexed-on-meta_key query across every tracked field at once,
	 * not a loop of get_posts() calls per key - this runs on every Media
	 * Library row, so it needs to stay cheap.
	 */
	public static function find_usage( $attachment_id ) {
		$attachment_id = (int) $attachment_id;
		if ( ! $attachment_id ) {
			return null;
		}
		if ( array_key_exists( $attachment_id, self::$cache ) ) {
			return self::$cache[ $attachment_id ];
		}

		global $wpdb;
		$all_keys     = array_merge( self::EPISODE_ATTACHMENT_KEYS, self::SHOW_ATTACHMENT_KEYS );
		$placeholders = implode( ', ', array_fill( 0, count( $all_keys ), '%s' ) );
		$sql          = $wpdb->prepare(
			"SELECT post_id, meta_key FROM {$wpdb->postmeta} WHERE meta_key IN ({$placeholders}) AND meta_value = %d LIMIT 1",
			array_merge( $all_keys, array( $attachment_id ) )
		);
		$row = $wpdb->get_row( $sql );

		if ( ! $row ) {
			self::$cache[ $attachment_id ] = null;
			return null;
		}

		$referencing_post_id = (int) $row->post_id;
		$is_episode_field    = in_array( $row->meta_key, self::EPISODE_ATTACHMENT_KEYS, true );
		$prefix              = $is_episode_field ? 'Episode: ' : 'Show setting: ';

		$result = array(
			'post_id' => $referencing_post_id,
			'label'   => $prefix . get_the_title( $referencing_post_id ),
		);
		self::$cache[ $attachment_id ] = $result;
		return $result;
	}
}
