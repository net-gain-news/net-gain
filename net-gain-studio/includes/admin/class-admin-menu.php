<?php
/**
 * Top-level "Net Gain Studio" menu (admin) plus "My Show" (talent-facing,
 * Phase 4 - the first non-admin-only screen). Detail/edit/review screens are
 * registered with a null parent so they're reachable by URL from list rows
 * without cluttering either menu.
 *
 * As of Phase 7, the Dashboard (Section 10) is the default page at the
 * top-level slug, not the Shows list - the dashboard is the daily-use
 * screen the spec frames it as; show setup is a less-frequent task, now
 * promoted to its own visible "Shows" submenu item instead.
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Net_Gain_Admin_Menu {

	const CAPABILITY = 'edit_ng_shows';
	const LIST_SLUG   = 'net-gain-studio'; // now the Dashboard - see class docblock.
	const SHOWS_SLUG  = 'net-gain-shows';
	const EDIT_SLUG   = 'net-gain-edit-show';

	private static $asset_hooks = array();

	public static function register() {
		add_menu_page(
			'Net Gain Studio',
			'Net Gain Studio',
			self::CAPABILITY,
			self::LIST_SLUG,
			array( 'Net_Gain_Dashboard_Page', 'render' ),
			'dashicons-microphone',
			26
		);

		add_submenu_page(
			self::LIST_SLUG,
			'Dashboard',
			'Dashboard',
			self::CAPABILITY,
			self::LIST_SLUG,
			array( 'Net_Gain_Dashboard_Page', 'render' )
		);

		add_submenu_page(
			self::LIST_SLUG,
			'Shows',
			'Shows',
			self::CAPABILITY,
			self::SHOWS_SLUG,
			array( 'Net_Gain_Shows_List_Page', 'render' )
		);

		self::$asset_hooks[] = add_submenu_page(
			null,
			'Edit Show',
			'Edit Show',
			self::CAPABILITY,
			self::EDIT_SLUG,
			array( 'Net_Gain_Edit_Show_Page', 'render' )
		);

		add_submenu_page(
			null,
			'Episodes',
			'Episodes',
			self::CAPABILITY,
			Net_Gain_Episodes_List_Page::SLUG,
			array( 'Net_Gain_Episodes_List_Page', 'render' )
		);

		add_submenu_page(
			null,
			'Episode Detail',
			'Episode Detail',
			self::CAPABILITY,
			Net_Gain_Episode_Detail_Page::SLUG,
			array( 'Net_Gain_Episode_Detail_Page', 'render' )
		);

		// Script review is reachable by admins and by assigned talent - gated inside
		// the page itself (a data relationship, not a capability), so the menu
		// registration capability here is just the base "read" (any logged-in user).
		self::$asset_hooks[] = add_submenu_page(
			null,
			'Script Review',
			'Script Review',
			'read',
			Net_Gain_Script_Review_Page::SLUG,
			array( 'Net_Gain_Script_Review_Page', 'render' )
		);

		self::$asset_hooks[] = add_menu_page(
			'My Show',
			'My Show',
			'read',
			Net_Gain_My_Show_Page::SLUG,
			array( 'Net_Gain_My_Show_Page', 'render' ),
			'dashicons-microphone',
			27
		);
	}

	public static function enqueue_assets( $hook ) {
		// CSS loads on every Net Gain Studio admin screen (it's small and shared -
		// form layout, frame pickers, and now the Phase 7 dashboard LEDs). JS/media
		// stay scoped to the specific pages that actually use them. Every one of our
		// page slugs starts with "net-gain", and WordPress derives the hook suffix
		// from the slug even for hidden (null-parent) pages, so this catches all of
		// them without needing to list every hook explicitly.
		if ( false === strpos( (string) $hook, 'net-gain' ) ) {
			return;
		}

		wp_enqueue_style( 'ng-admin', plugins_url( 'assets/admin.css', NET_GAIN_PLUGIN_FILE ), array(), NET_GAIN_VERSION );

		if ( ! in_array( $hook, self::$asset_hooks, true ) ) {
			return;
		}

		wp_enqueue_media();
		wp_enqueue_script( 'ng-admin', plugins_url( 'assets/admin.js', NET_GAIN_PLUGIN_FILE ), array( 'jquery' ), NET_GAIN_VERSION, true );
		wp_localize_script( 'ng-admin', 'ngAdmin', array(
			'restUrl' => esc_url_raw( rest_url( 'net-gain/v1' ) ),
			'apiRoot' => esc_url_raw( rest_url() ),
			'nonce'   => wp_create_nonce( 'wp_rest' ),
		) );
	}
}
