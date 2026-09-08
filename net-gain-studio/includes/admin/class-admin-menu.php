<?php
/**
 * Top-level "Net Gain Studio" menu. Only the Shows list is a visible nav
 * item; Add/Edit Show is registered with a null parent so it's reachable by
 * URL (from the list's row/"Add New" links) without cluttering the menu.
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Net_Gain_Admin_Menu {

	const CAPABILITY = 'edit_ng_shows';
	const LIST_SLUG  = 'net-gain-studio';
	const EDIT_SLUG  = 'net-gain-edit-show';

	private static $edit_page_hook;

	public static function register() {
		add_menu_page(
			'Net Gain Studio',
			'Net Gain Studio',
			self::CAPABILITY,
			self::LIST_SLUG,
			array( 'Net_Gain_Shows_List_Page', 'render' ),
			'dashicons-microphone',
			26
		);

		self::$edit_page_hook = add_submenu_page(
			null,
			'Edit Show',
			'Edit Show',
			self::CAPABILITY,
			self::EDIT_SLUG,
			array( 'Net_Gain_Edit_Show_Page', 'render' )
		);
	}

	public static function enqueue_assets( $hook ) {
		if ( self::$edit_page_hook !== $hook ) {
			return;
		}

		wp_enqueue_media();
		wp_enqueue_style( 'ng-admin', plugins_url( 'assets/admin.css', NET_GAIN_PLUGIN_FILE ), array(), NET_GAIN_VERSION );
		wp_enqueue_script( 'ng-admin', plugins_url( 'assets/admin.js', NET_GAIN_PLUGIN_FILE ), array( 'jquery' ), NET_GAIN_VERSION, true );
	}
}
